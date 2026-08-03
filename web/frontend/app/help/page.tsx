import Link from "next/link";
import StaticPage, { Section } from "@/components/StaticPage";

export default function HelpCenterPage() {
  return (
    <StaticPage title="Help Center" subtitle="Common questions about building with BrickForgerAI.">
      <Section title="How many credits do I get?">
        <p>
          Free accounts get 10 build credits a month; Pro accounts get 30. One credit is used
          each time you generate a model. Credits reset at the start of each calendar month.
          See the <Link href="/pricing">Pricing</Link> page for full plan details.
        </p>
      </Section>
      <Section title="What's the difference between the preview and the instructions?">
        <p>
          Every generation gives you a full 3D preview (with real colors) and the raw{" "}
          <code>.ldr</code> file for free. &ldquo;Instructions&rdquo; refers to a polished,
          step-by-step build guide and parts list — included automatically on the Pro plan, or
          available as a one-time purchase (£5–£15, based on model size) on the Free plan.
        </p>
      </Section>
      <Section title="A generation failed — what do I do?">
        <p>
          Click through to the model&apos;s page and check the error message shown there.
          Generation runs in three stages (image, 3D shape, then bricks) and can fail at any
          of them — most often a temporary issue with the image or 3D generation services.
          Failed generations still use a credit; try again with a slightly different prompt if
          it keeps failing.
        </p>
      </Section>
      <Section title="Why do the colors sometimes look a little off?">
        <p>
          Colors are estimated from the reference image and mapped onto a limited palette of
          real, purchasable brick colors — so they&apos;re an approximation, not an exact match,
          especially on parts of the model not clearly visible in the reference image.
        </p>
      </Section>
      <Section title="Can I build what I generate with real bricks?">
        <p>
          Yes — every part in a generated model is a real, standard brick/plate/tile/slope
          shape. Open the downloaded <code>.ldr</code> file in BrickLink Studio to get a parts
          list you can buy from BrickLink.
        </p>
      </Section>
      <Section title="Still stuck?">
        <p>This is a trial version of BrickForgerAI — support is informal for now. Reach out however you got this link.</p>
      </Section>
    </StaticPage>
  );
}
