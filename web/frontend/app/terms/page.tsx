import StaticPage, { Section } from "@/components/StaticPage";

export default function TermsPage() {
  return (
    <StaticPage
      title="Terms of Service"
      subtitle="Trial-stage placeholder text — not final, lawyer-reviewed terms. Read before treating this as binding."
    >
      <Section title="What this service does">
        <p>
          BrickForgerAI turns a text description into a 3D model built from real,
          LEGO-compatible brick, plate, tile, and slope shapes, exported as an{" "}
          <code>.ldr</code> file.
        </p>
      </Section>
      <Section title="Trademark disclaimer">
        <p>
          BrickForgerAI is not affiliated with, endorsed by, or sponsored by the LEGO Group.
          &ldquo;LEGO&rdquo; is a registered trademark of the LEGO Group. Part geometry is
          drawn from the LDraw parts library, licensed under CCAL 2.0.
        </p>
      </Section>
      <Section title="Your prompts and content">
        <p>
          Generate original designs — don&apos;t prompt for copyrighted characters, logos, or
          existing commercial LEGO sets. Content that appears to target a specific copyrighted
          character or trademark may be refused or removed. You&apos;re responsible for what
          you type in and for how you use the resulting files.
        </p>
      </Section>
      <Section title="Credits and plans">
        <p>
          The Free plan includes 10 model generations a month; the Master Builder plan includes 30, plus
          instruction unlocks included on every generation. Unused credits do not roll over
          between months. Payment processing for the Master Builder plan is not live yet in this trial
          version.
        </p>
      </Section>
      <Section title="No warranty">
        <p>
          Generated models are produced automatically and are not guaranteed to be physically
          buildable, structurally sound, or free of errors — always check a generated model in
          BrickLink Studio (or by hand) before ordering parts or building.
        </p>
      </Section>
      <Section title="Changes">
        <p>This is a trial product and these terms may change at any time without notice.</p>
      </Section>
    </StaticPage>
  );
}
