"""Stage: reference image -> 3D mesh file (.glb)."""
from __future__ import annotations

import base64
import json
import os
import random
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
        self._randomize_seeds(workflow)
        return workflow

    @staticmethod
    def _randomize_seeds(workflow: dict[str, Any]) -> None:
        """Every `seed` input in the checked-in workflow JSON
        (trellis_workflow_api.json) is a hardcoded 12345 -- both the shape
        generator's and the texturing node's. Real bug, not a style nit:
        every job's diffusion sampling was running with *identical* noise
        regardless of the prompt or reference image, which means any
        seed-specific sampling artifact (confirmed on a real job: a pear's
        baked texture came back with its blue channel collapsed to ~0
        across the whole mesh, while a cactus job with the same fixed seed
        was fine) would deterministically hit every single future job with
        similar-enough conditioning, not just one unlucky run. Randomizing
        per job is the actual fix -- a bad draw becomes rare and
        non-reproducible instead of baked into the app permanently."""
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if isinstance(inputs, dict) and "seed" in inputs and isinstance(inputs["seed"], int):
                inputs["seed"] = random.randint(0, 2**31 - 1)

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


class FalTrellis2Client(MeshGenClient):
    """image -> 3D mesh via fal.ai's hosted `fal-ai/trellis-2` -- the
    commercial equivalent of the local TRELLIS 2 + Trellis2MeshTexturing
    ComfyUI workflow this project otherwise runs.

    Deliberately NOT `fal-ai/trellis` (the original model): that one is
    shape-only, same as this project's TRELLIS workflow before it was
    upgraded to TRELLIS 2 (see CLAUDE.md's "colors were genuinely broken
    end to end" section). Using it here would silently reproduce that bug
    and reactivate `reference_color.py`'s photo-projection fallback for
    every job, not just the ones that need it.

    Uses fal's async queue API directly over `requests` rather than the
    `fal-client` SDK -- the queue protocol (submit -> poll status_url ->
    fetch response_url) is a handful of plain HTTP calls, matching the
    style already used for Meshy and local ComfyUI in this file, with no
    SDK dependency to add.
    """

    QUEUE_BASE_URL = "https://queue.fal.run/fal-ai/trellis-2"

    def __init__(
        self,
        api_key: str,
        resolution: int = 1024,
        poll_interval_s: float = 5.0,
        timeout_s: float = 600.0,
    ):
        self.api_key = api_key
        self.resolution = resolution
        self.poll_interval_s = poll_interval_s
        self.timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _image_to_data_uri(image_path: str) -> str:
        """fal's queue API accepts a file input as either a public URL or
        an inline base64 data URI -- a data URI avoids a separate upload
        round-trip, and is fine at this size (a single reference photo,
        not the resulting mesh). Re-encoded through PIL as RGBA PNG for
        the same reason TrellisComfyUIClient does: normalizes whatever
        format the upstream image-gen step produced."""
        image_path_obj = Path(image_path)
        if not image_path_obj.is_file():
            raise FileNotFoundError(f"Input image does not exist: {image_path_obj}")
        with Image.open(image_path_obj) as image:
            buffer = BytesIO()
            image.convert("RGBA").save(buffer, format="PNG")
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def generate(self, image_path: str, out_path: str) -> str:
        out_path_obj = Path(out_path)
        out_path_obj.parent.mkdir(parents=True, exist_ok=True)

        image_data_uri = self._image_to_data_uri(image_path)

        submit_response = requests.post(
            self.QUEUE_BASE_URL,
            headers=self._headers(),
            json={"image_url": image_data_uri, "resolution": self.resolution},
            timeout=60,
        )
        submit_response.raise_for_status()
        submit_data = submit_response.json()
        request_id = submit_data.get("request_id")
        status_url = submit_data.get("status_url")
        response_url = submit_data.get("response_url")
        if not request_id or not status_url or not response_url:
            raise RuntimeError(f"fal did not return the expected queue URLs. Response: {submit_data}")

        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            status_response = requests.get(status_url, headers=self._headers(), timeout=30)
            status_response.raise_for_status()
            status_data = status_response.json()
            status = status_data.get("status")

            if status == "COMPLETED":
                error = status_data.get("error")
                if error:
                    raise RuntimeError(
                        f"fal-ai/trellis-2 generation failed ({status_data.get('error_type')}): {error}"
                    )

                result_response = requests.get(response_url, headers=self._headers(), timeout=30)
                result_response.raise_for_status()
                result_data = result_response.json()
                model_glb = result_data.get("model_glb") or {}
                glb_url = model_glb.get("url")
                if not glb_url:
                    raise RuntimeError(
                        f"fal-ai/trellis-2 completed but did not return a model_glb URL. Response: {result_data}"
                    )

                glb_response = requests.get(glb_url, timeout=120)
                glb_response.raise_for_status()
                out_path_obj.write_bytes(glb_response.content)
                if out_path_obj.stat().st_size == 0:
                    raise RuntimeError(f"fal-ai/trellis-2 returned an empty mesh file: {out_path_obj}")
                return str(out_path_obj)

            time.sleep(self.poll_interval_s)

        raise TimeoutError(
            f"fal-ai/trellis-2 generation did not complete within {self.timeout_s} seconds. Request ID: {request_id}"
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

    if provider == "fal_trellis2":
        api_key = os.environ.get("FAL_KEY")
        if not api_key:
            raise RuntimeError("MESH_GEN_PROVIDER is set to 'fal_trellis2', but FAL_KEY is missing.")
        return FalTrellis2Client(
            api_key=api_key,
            resolution=int(os.environ.get("FAL_TRELLIS2_RESOLUTION", "1024")),
            poll_interval_s=float(os.environ.get("FAL_TRELLIS2_POLL_INTERVAL_S", "5")),
            timeout_s=float(os.environ.get("FAL_TRELLIS2_TIMEOUT_S", "600")),
        )

    raise ValueError(
        f"Unknown MESH_GEN_PROVIDER: {provider!r}. Expected 'meshy', 'trellis_local', or 'fal_trellis2'."
    )
