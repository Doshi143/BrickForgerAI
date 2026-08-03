import StaticPage, { Section } from "@/components/StaticPage";

export default function PrivacyPage() {
  return (
    <StaticPage
      title="Privacy Policy"
      subtitle="Trial-stage placeholder text — not final, lawyer-reviewed terms. Read before treating this as binding."
    >
      <Section title="What we store">
        <p>
          Your email address and a hashed (never plain-text) password, plus the prompts you
          submit and the images, 3D meshes, and brick models generated from them. This trial
          version stores everything locally on the server it runs on — there is no
          third-party analytics or advertising tracking.
        </p>
      </Section>
      <Section title="Who else sees your data">
        <p>
          Your prompt (rewritten into an image-generation instruction) is sent to OpenAI to
          generate a reference image, and that image is sent to a 3D-reconstruction model to
          generate a mesh. No other third parties receive your prompts or generated content.
        </p>
      </Section>
      <Section title="How long we keep it">
        <p>
          Generated models and account data are kept for as long as this trial is running.
          Since this is a trial, not a production service, data may be cleared during
          development without notice.
        </p>
      </Section>
      <Section title="Your choices">
        <p>You can stop using the service at any time. There's no account-deletion flow built yet in this trial version.</p>
      </Section>
    </StaticPage>
  );
}
