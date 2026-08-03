"""Stage: reference image -> 3D mesh file (.glb)."""
from __future__ import annotations

import json
import os
import shutil
import time
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image


class MeshGenClient(ABC):
    @abstractmethod
    def generate(self, image_path: str, out_path: str) -> str:
        raise NotImplementedError


class StubMeshGenClient(MeshGenClient):
    def generate(self, image_path: str, out_path: str) -> str:
        raise NotImplementedError(
            "No mesh generation provider configured. Set MESH_GEN_PROVIDER and the matching API key env var."
        )


class MeshyClient(MeshGenClient):
    BASE_URL = "https://api.meshy.ai"

    def __init__(self, api_key: str, poll_interval_s: float = 5.0, timeout_s: float = 300.0):
        self.api_key = api_key
        self.poll_interval_s = poll_interval_s
        self.timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def generate(self, image_path: str, out_path: str) -> str:
        image_path_obj = Path(image_path)
        out_path_obj = Path(out_path)

        if not image_path_obj.is_file():
            raise FileNotFoundError(f"Input image does not exist: {image_path_obj}")

        out_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with image_path_obj.open("rb") as image_file:
            response = requests.post(
                f"{self.BASE_URL}/v1/image-to-3d",
                headers=self._headers(),
                files={"image": image_file},
                timeout=60,
            )

        response.raise_for_status()
        response_data = response.json()
        job_id = response_data.get("id")
        if not job_id:
            raise RuntimeError(f"Meshy did not return a job ID. Response: {response_data}")

        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            status_response = requests.get(
                f"{self.BASE_URL}/v1/image-to-3d/{job_id}",
                headers=self._headers(),
                timeout=30,
            )
            status_response.raise_for_status()
            data = status_response.json()
            status = data.get("status")

            if status == "SUCCEEDED":
                model_urls = data.get("model_urls", {})
                model_url = model_urls.get("glb")
                if not model_url:
                    raise RuntimeError(f"Meshy completed the generation but did not return a GLB URL. Response: {data}")
                model_response = requests.get(model_url, timeout=120)
                model_response.raise_for_status()
                out_path_obj.write_bytes(model_response.content)
                return str(out_path_obj)

            if status == "FAILED":
                raise RuntimeError(f"Meshy generation failed: {data}")

            time.sleep(self.poll_interval_s)

        raise TimeoutError(f"Meshy generation did not complete within {self.timeout_s} seconds. Job ID: {job_id}")


class TrellisComfyUIClient(MeshGenClient):
    def __init__(
        self,
        workflow_json_path: str,
        comfyui_url: str = "http://127.0.0.1:8188",
        image_input_node_id: str = "6",
        output_node_id: str = "232",
        poll_interval_s: float = 3.0,
        timeout_s: float = 1800.0,
    ):
        self.comfyui_url = comfyui_url.rstrip("/")
        self.workflow_json_path = workflow_json_path
        self.image_input_node_id = str(image_input_node_id)
        self.output_node_id = str(output_node_id)
        self.poll_interval_s = poll_interval_s
        self.timeout_s = timeout_s

    def _load_workflow(self) -> dict[str, Any]:
        workflow_path = Path(self.workflow_json_path)
        if not workflow_path.is_file():
            raise FileNotFoundError(f"TRELLIS workflow JSON does not exist: {workflow_path}")
        with workflow_path.open("r", encoding="utf-8") as f:
            workflow = json.load(f)
        if not isinstance(workflow, dict):
            raise RuntimeError("The TRELLIS workflow JSON must contain a JSON object.")
        return workflow

    def _upload_image(self, image_path: str) -> str:
        image_path_obj = Path(image_path)
        if not image_path_obj.is_file():
            raise FileNotFoundError(f"Input image does not exist: {image_path_obj}")

        image_buffer = BytesIO()
        with Image.open(image_path_obj) as image:
            rgba_image = image.convert("RGBA")
            rgba_image.save(image_buffer, format="PNG")
        image_buffer.seek(0)

        try:
            response = requests.post(
                f"{self.comfyui_url}/upload/image",
                files={"image": ("trellis_input.png", image_buffer, "image/png")},
                timeout=30,
            )
        finally:
            image_buffer.close()

        response.raise_for_status()
        response_data = response.json()
        uploaded_name = response_data.get("name")
        if not uploaded_name:
            raise RuntimeError(
                "ComfyUI uploaded the image but did not return a filename. "
                f"Response: {response_data}"
            )
        return uploaded_name

    def _prepare_workflow(self, uploaded_filename: str) -> dict[str, Any]:
        workflow = self._load_workflow()
        if self.image_input_node_id not in workflow:
            raise RuntimeError(
                f"Image input node {self.image_input_node_id!r} was not found in the workflow. Available node IDs: {list(workflow.keys())}"
            )
        image_node = workflow[self.image_input_node_id]
        if not isinstance(image_node, dict):
            raise RuntimeError(f"Image input node {self.image_input_node_id!r} does not contain valid node data.")
        inputs = image_node.get("inputs")
        if not isinstance(inputs, dict):
            raise RuntimeError(f"Image input node {self.image_input_node_id!r} does not contain an inputs object.")
        if "image" not in inputs:
            raise RuntimeError(f"Node {self.image_input_node_id!r} does not have an 'image' input. Node class: {image_node.get('class_type')!r}")
        inputs["image"] = uploaded_filename
        return workflow

    def _queue_workflow(self, workflow: dict[str, Any]) -> str:
        response = requests.post(
            f"{self.comfyui_url}/prompt",
            json={"prompt": workflow},
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"ComfyUI rejected the workflow. HTTP {response.status_code}: {response.text}")
        response_data = response.json()
        prompt_id = response_data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return a prompt ID. Response: {response_data}")
        return str(prompt_id)

    @staticmethod
    def _extract_error_message(messages: Any) -> str:
        if not messages:
            return "No detailed ComfyUI error message was returned."
        try:
            return json.dumps(messages, indent=2, default=str)
        except (TypeError, ValueError):
            return str(messages)

    @staticmethod
    def _extract_result_path(node_output: dict[str, Any]) -> Path | None:
        result = node_output.get("result")
        if isinstance(result, list) and result and isinstance(result[0], str):
            return Path(result[0])
        return None

    @staticmethod
    def _find_file_list(node_output: dict[str, Any]) -> list[dict[str, Any]] | None:
        for key in ("meshes", "files", "glb", "gltf", "images"):
            value = node_output.get(key)
            if isinstance(value, list) and value:
                return value
        return None

    def _save_output_path(self, source_path: Path, out_path: str) -> str:
        if not source_path.is_file():
            raise RuntimeError(f"The generated file does not exist: {source_path}")
        out_path_obj = Path(out_path)
        out_path_obj.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, out_path_obj)
        if not out_path_obj.is_file() or out_path_obj.stat().st_size == 0:
            raise RuntimeError(f"Failed to save the generated mesh to {out_path_obj}")
        return str(out_path_obj)

    def _download_output(self, file_info: dict[str, Any], out_path: str) -> str:
        filename = file_info.get("filename")
        if not filename:
            raise RuntimeError(
                "The TRELLIS output did not include a filename. "
                f"File information: {file_info}"
            )
        response = requests.get(
            f"{self.comfyui_url}/view",
            params={
                "filename": filename,
                "subfolder": file_info.get("subfolder", ""),
                "type": file_info.get("type", "output"),
            },
            timeout=300,
        )
        response.raise_for_status()
        out_path_obj = Path(out_path)
        out_path_obj.parent.mkdir(parents=True, exist_ok=True)
        out_path_obj.write_bytes(response.content)
        if not out_path_obj.is_file() or out_path_obj.stat().st_size == 0:
            raise RuntimeError(f"ComfyUI returned an empty output file: {out_path_obj}")
        return str(out_path_obj)

    def generate(self, image_path: str, out_path: str) -> str:
        uploaded_filename = self._upload_image(image_path)
        workflow = self._prepare_workflow(uploaded_filename)
        prompt_id = self._queue_workflow(workflow)

        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            try:
                history_response = requests.get(f"{self.comfyui_url}/history/{prompt_id}", timeout=120)
            except requests.exceptions.ReadTimeout:
                time.sleep(self.poll_interval_s)
                continue

            history_response.raise_for_status()
            history = history_response.json()
            prompt_history = history.get(prompt_id)
            if prompt_history is None:
                time.sleep(self.poll_interval_s)
                continue

            status_info = prompt_history.get("status", {})
            if status_info.get("status_str") == "error":
                raise RuntimeError(
                    "ComfyUI/TRELLIS execution failed.\n"
                    f"Prompt ID: {prompt_id}\n"
                    f"Details:\n{self._extract_error_message(status_info.get('messages', []))}"
                )

            if not status_info.get("completed", False):
                time.sleep(self.poll_interval_s)
                continue

            outputs = prompt_history.get("outputs", {})
            if not isinstance(outputs, dict):
                raise RuntimeError(f"ComfyUI completed, but its outputs field was invalid. Outputs: {outputs}")

            node_output = outputs.get(self.output_node_id)
            if node_output is None:
                raise RuntimeError(
                    f"ComfyUI completed, but output node {self.output_node_id!r} was not found in the history. Available output nodes: {list(outputs.keys())}. Status messages: {self._extract_error_message(status_info.get('messages', []))}"
                )
            if not isinstance(node_output, dict):
                raise RuntimeError(f"Output node {self.output_node_id!r} returned an unexpected value: {node_output}")

            result_path = self._extract_result_path(node_output)
            if result_path is not None:
                return self._save_output_path(result_path, out_path)

            file_list = self._find_file_list(node_output)
            if file_list:
                file_info = file_list[0]
                if not isinstance(file_info, dict):
                    raise RuntimeError(f"The TRELLIS output file information was invalid. Value: {file_info}")
                return self._download_output(file_info=file_info, out_path=out_path)

            raise RuntimeError(
                f"Output node {self.output_node_id!r} was found, but it did not report a downloadable file. Node output: {node_output}"
            )

        raise TimeoutError(
            f"TRELLIS 2 generation did not complete within {self.timeout_s} seconds. Prompt ID: {prompt_id}"
        )


def get_mesh_client() -> MeshGenClient:
    provider = os.environ.get("MESH_GEN_PROVIDER", "").strip().lower()

    if not provider:
        return StubMeshGenClient()

    if provider == "meshy":
        api_key = os.environ.get("MESHY_API_KEY")
        if not api_key:
            raise RuntimeError("MESH_GEN_PROVIDER is set to 'meshy', but MESHY_API_KEY is missing.")
        return MeshyClient(
            api_key=api_key,
            poll_interval_s=float(os.environ.get("MESHY_POLL_INTERVAL_S", "5")),
            timeout_s=float(os.environ.get("MESHY_TIMEOUT_S", "300")),
        )

    if provider == "trellis_local":
        default_workflow_path = os.path.join(os.path.dirname(__file__), "trellis_workflow_api.json")
        return TrellisComfyUIClient(
            workflow_json_path=os.environ.get("TRELLIS_WORKFLOW_JSON", default_workflow_path),
            comfyui_url=os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"),
            image_input_node_id=os.environ.get("TRELLIS_IMAGE_NODE_ID", "6"),
            output_node_id=os.environ.get("TRELLIS_OUTPUT_NODE_ID", "232"),
            poll_interval_s=float(os.environ.get("TRELLIS_POLL_INTERVAL_S", "3")),
            timeout_s=float(os.environ.get("TRELLIS_TIMEOUT_S", "1800")),
        )

    raise ValueError(f"Unknown MESH_GEN_PROVIDER: {provider!r}. Expected 'meshy' or 'trellis_local'.")
