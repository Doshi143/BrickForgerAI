import Link from "next/link";
import StaticPage, { Section } from "@/components/StaticPage";

export default function HelpCenterPage() {
  return (
    <StaticPage title="Help Center" subtitle="Common questions about building with BrickForgerAI.">
      <Section title="How many credits do I get?">
        <p>
          Free accounts get 5 build credits a month, Builder gets 12, and Master Builder gets 30.
          One credit is used each time you generate a model. Credits reset at the start of each
          calendar month, and you can always buy +5 credits for £6 on top of your current plan.
          See the <Link href="/pricing">Pricing</Link> page for full plan details.
        </p>
      </Section>
      <Section title="What's the difference between the preview and the instructions?">
        <p>
          Every generation gives you a full 3D preview (with real colors) and the raw{" "}
          <code>.ldr</code> file for free. &ldquo;Instructions&rdquo; refers to a polished,
          step-by-step build guide and parts list — included automatically on the Master Builder plan, or
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
          Color comes straight from the generated 3D model&apos;s own surface, then gets mapped
          onto the closest real, purchasable brick color using a perceptually-accurate color
          match — so it&apos;s a close approximation, not an exact one, especially on faces of the
          model that came through less clearly during generation.
        </p>
      </Section>
      <Section title="Can I build what I generate with real bricks?">
        <p>
          Yes — every part in a generated model is a real, standard brick/plate/tile/slope
          shape. Open the downloaded <code>.ldr</code> file in BrickLink Studio to get a parts
          list you can buy from BrickLink.
        </p>
      </Section>
      <Section title="Will my model actually be physically stable?">
        <p>
          We can&apos;t guarantee that every generated model will be very physically stable —
          it depends on what you asked for and how thin or overhanging the shape is. What we
          can say is that the vast majority of generated models come out with 100% connectivity
          and few flagged issues on BrickLink Studio&apos;s own stability checker, thanks to a
          built-in support-structure algorithm that automatically finds and braces weak points
          before a model is finished. Always give a model a quick check in Studio (or by hand)
          before ordering parts, especially for anything thin, tall, or overhanging.
        </p>
      </Section>
      <Section title="Still stuck?">
        <p>
          This is a trial version of BrickForgerAI — support is informal for now, but you can
          reach us directly at{" "}
          <a href="mailto:help@brickforgerai.com" style={{ color: "inherit" }}>
            help@brickforgerai.com
          </a>
          .
        </p>
      </Section>
    </StaticPage>
  );
}
