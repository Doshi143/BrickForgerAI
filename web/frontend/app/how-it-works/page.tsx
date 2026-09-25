import Link from "next/link";
import StaticPage, { Section } from "@/components/StaticPage";

export default function HowItWorksPage() {
  return (
    <StaticPage title="How it works" subtitle="Describe it. We build it out of real bricks.">
      <Section title="1. Describe what you want to build">
        <p>
          Type a description - anything from &ldquo;a small red sports car&rdquo; to
          &ldquo;a stylized cartoon pineapple.&rdquo; Use the build size slider to set how many
          studs across the finished model is - bigger means more detail and more parts.
        </p>
      </Section>
      <Section title="2. We build it">
        <p>
          Behind the scenes, your description becomes a real, physically buildable model made
          entirely from standard, purchasable brick, plate, tile, and slope pieces - checked so
          it won&apos;t fall apart when picked up. There are two ways to build it:
        </p>
        <ul style={{ paddingLeft: 20, lineHeight: 1.8 }}>
          <li>
            <strong>Voxel</strong> (1 credit) - your prompt becomes a picture, then a 3D shape,
            which is then filled with bricks. Best on organic shapes like animals, plants, and
            sculptures.
          </li>
          <li>
            <strong>Detailed</strong> (beta, 2 credits) - the model is designed piece by piece
            using real building techniques: curved slopes, smooth tiles, real wheels, windows and
            doors, and optional sideways building. Best on buildings, vehicles, and animals. You
            choose the finish (smooth tiles or studs showing) and how much sideways building to
            use. Detailed is being rolled out gradually, so it may not show on your account yet.
          </li>
        </ul>
      </Section>
      <Section title="3. What every plan includes">
        <p>Every generation, on every plan, includes:</p>
        <ul style={{ paddingLeft: 20, lineHeight: 1.8 }}>
          <li>A live 3D preview you can rotate and zoom, in real part colors</li>
          <li>A part count and color breakdown</li>
          <li>The downloadable .ldr file, a full parts list, and a step-by-step PDF build guide - included automatically, no separate purchase needed</li>
        </ul>
        <p>
          The build guide walks through the model bottom-up, layer by layer, with the new
          pieces highlighted at each step. You can also open the .ldr file in BrickLink Studio
          (free) to check the parts list against real BrickLink inventory. See{" "}
          <Link href="/pricing">Pricing</Link> for full plan details.
        </p>
      </Section>
    </StaticPage>
  );
}
