import Link from "next/link";
import StaticPage, { Section } from "@/components/StaticPage";

export default function HelpCenterPage() {
  return (
    <StaticPage title="Help Center" subtitle="Common questions about building with BrickForgerAI.">
      <Section title="How many credits do I get?">
        <p>
          Starter gets 3 build credits a month, Builder gets 12, and Master Builder gets 30.
          A Voxel generation uses one credit and a Detailed (beta) generation uses two. If a
          Detailed generation can&apos;t produce a model that holds together, both credits are
          refunded automatically. Credits reset at the start of each
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
          automatically on every current plan (Starter, Builder, and Master Builder). You can
          also open the{" "}
          <code>.ldr</code> file in BrickLink Studio (free, search &ldquo;BrickLink Studio
          download&rdquo;) to check the parts list against real BrickLink inventory.
        </p>
      </Section>
      <Section title="Why do the colors sometimes look a little off?">
        <p>
          In Voxel mode, color comes straight from the generated 3D model&apos;s own surface,
          then gets mapped onto the closest real, purchasable brick color using a
          perceptually-accurate color match - so it&apos;s a close approximation, not an exact one,
          especially on faces of the model that came through less clearly during generation. In
          Detailed mode, colors are picked from real brick colors as the model is designed, so
          they are exact brick colors, but still an interpretation of your prompt.
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
      <Section title="What's actually in the brick library?">
        <p>
          Voxel generations are built from a 55-part real, purchasable brick library - bricks,
          plates, tiles, and a wide range of slope angles and curves for smoother, less blocky
          surfaces. Detailed generations use a 70+ part library that adds curved slopes, round
          bricks, windows, doors, real wheels, plants, and sideways building (also known as SNOT -
          &ldquo;Studs Not On Top&rdquo;) for more detailed, less boxy shapes. Both are growing
          all the time as we add new building techniques.
        </p>
      </Section>
      <Section title="What kinds of prompts work best?">
        <p>
          Voxel is strongest on organic shapes - animals, plants, and sculptural forms in
          particular. Detailed is strongest on buildings, vehicles, and animals, and weaker on
          very thin or flat subjects (long tentacles, instruments lying flat). Either way, the
          more specific your prompt, the better the result: describing pose, proportions, or
          distinctive features gives the generator more to work with than a one-word prompt.
        </p>
      </Section>
      <Section title="Can I ask for specific bricks, slopes, or a part count in my prompt?">
        <p>
          No - your prompt only describes what to build, and the builder picks parts on its own,
          so instructions like &ldquo;use curved slopes&rdquo;, &ldquo;avoid 1x1 plates&rdquo;, or
          &ldquo;150 to 300 parts&rdquo; are ignored. In Voxel mode your prompt becomes an image,
          then a 3D shape, and only then does the brick builder run; slopes and sideways (SNOT)
          pieces only appear where the shape has a suitable step or flat wall, so smooth curves on
          things like a bird&apos;s back or neck will still come out slightly stepped. In Detailed
          mode you can choose the building style with the controls under the prompt instead: the
          finish (smooth tiles or studs showing) and how much sideways building to use. Spend your
          prompt on the subject: pose, proportions, colors, and distinctive features, and use the
          build size slider to control how detailed the build is.
        </p>
      </Section>
      <Section title="Will my model actually be physically stable?">
        <p>
          We can&apos;t guarantee that every generated model will be very physically stable -
          it depends on what you asked for and how thin or overhanging the shape is. What we
          can say is that the vast majority of generated models come out with 100% connectivity
          and few flagged issues on BrickLink Studio&apos;s own stability checker, thanks to a
          built-in support-structure algorithm that automatically finds and braces weak points
          before a model is finished. Detailed models are checked so every part connects and
          nothing overlaps, but they don&apos;t get Voxel mode&apos;s load analysis. Always give a model a quick check in Studio (or by hand)
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
