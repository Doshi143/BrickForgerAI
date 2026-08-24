import Link from "next/link";
import StaticPage, { Section } from "@/components/StaticPage";

export default function HowItWorksPage() {
  return (
    <StaticPage title="How it works" subtitle="Describe it. We build it out of real bricks.">
      <Section title="1. Describe what you want to build">
        <p>
          Type a description — anything from &ldquo;a small red sports car&rdquo; to
          &ldquo;a stylized cartoon pineapple.&rdquo; Pick a build size (Small, Medium,
          or Large) to control roughly how big and detailed the finished model is.
        </p>
      </Section>
      <Section title="2. We build it">
        <p>
          Behind the scenes, your description becomes a real, physically buildable model made
          entirely from standard, purchasable brick, plate, tile, and slope pieces — checked so
          it won&apos;t fall apart when picked up.
        </p>
      </Section>
      <Section title="3. What you get depends on your plan">
        <p>Every generation, on every plan, includes:</p>
        <ul style={{ paddingLeft: 20, lineHeight: 1.8 }}>
          <li>A live 3D preview you can rotate and zoom, in real part colors</li>
          <li>A part count and color breakdown</li>
        </ul>
        <p>
          To actually build it, you need the downloadable .ldr file, parts list, and PDF build
          guide:
        </p>
        <ul style={{ paddingLeft: 20, lineHeight: 1.8 }}>
          <li>
            <strong>Free plan</strong> — unlock the download for an individual model for
            £5–£15 (based on size)
          </li>
          <li>
            <strong>Builder and Master Builder plans</strong> — downloads are included
            automatically on every generation
          </li>
        </ul>
        <p>
          Unlocking a model gets you the .ldr file, a full parts list, and a step-by-step PDF
          build guide — walking through the model bottom-up, layer by layer, with the new
          pieces highlighted at each step. You can also open the .ldr file in BrickLink Studio
          (free) to check the parts list against real BrickLink inventory. See{" "}
          <Link href="/pricing">Pricing</Link> for full plan details.
        </p>
      </Section>
    </StaticPage>
  );
}
