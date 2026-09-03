import Link from "next/link";
import StaticPage, { Section } from "@/components/StaticPage";

export default function HelpCenterPage() {
  return (
    <StaticPage title="Help Center" subtitle="Common questions about building with BrickForgerAI.">
      <Section title="How many credits do I get?">
        <p>
          Free accounts get 3 build credits a month, Builder gets 12, and Master Builder gets 30.
          One credit is used each time you generate a model. Credits reset at the start of each
          calendar month, and you can always buy +5 credits for £6 on top of your current plan.
          See the <Link href="/pricing">Pricing</Link> page for full plan details.
        </p>
      </Section>
      <Section title="What's the difference between the preview and the instructions?">
        <p>
          Every generation gives you a full 3D preview (with real colors) for free - you can
          rotate and inspect the model, and see its part count and color breakdown, without
          paying anything. &ldquo;Instructions&rdquo; is the downloadable <code>.ldr</code> file,
          full parts list, and a step-by-step PDF build guide - walking through the model
          bottom-up, layer by layer, with the new pieces for each step called out - included
          automatically on the Builder and Master Builder plans, or available as a one-time
          purchase (£5–£15, based on model size) on the Free plan. You can also open the{" "}
          <code>.ldr</code> file in BrickLink Studio (free, search &ldquo;BrickLink Studio
          download&rdquo;) to check the parts list against real BrickLink inventory.
        </p>
      </Section>
      <Section title="Why do the colors sometimes look a little off?">
        <p>
          Color comes straight from the generated 3D model&apos;s own surface, then gets mapped
          onto the closest real, purchasable brick color using a perceptually-accurate color
          match - so it&apos;s a close approximation, not an exact one, especially on faces of the
          model that came through less clearly during generation.
        </p>
      </Section>
      <Section title="Can I build what I generate with real bricks?">
        <p>
          Yes - every part in a generated model is a real, standard brick/plate/tile/slope
          shape. Unlocking a model gets you the <code>.ldr</code> file, a full parts list, and
          a PDF build guide; from there you can buy the parts from BrickLink or open the{" "}
          <code>.ldr</code> file in BrickLink Studio for its own inventory check.
        </p>
      </Section>
      <Section title="Will my model actually be physically stable?">
        <p>
          We can&apos;t guarantee that every generated model will be very physically stable -
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
          This is a trial version of BrickForgerAI - support is informal for now, but you can
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
