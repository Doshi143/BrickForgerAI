import StaticPage, { Section } from "@/components/StaticPage";

export default function PrivacyPage() {
  return (
    <StaticPage title="Privacy Policy" subtitle="Last updated August 6th, 2026">
      <Section title="Overview">
        <p>
          BrickForgerAI (&ldquo;we,&rdquo; &ldquo;our,&rdquo; or &ldquo;us&rdquo;) is committed
          to protecting your privacy. This Privacy Policy explains how your personal information
          is collected, used, and disclosed when you use our website and its associated
          subdomains (together, our &ldquo;Service&rdquo;). By using the Service, you agree to
          the collection, storage, use, and disclosure of your information as described here and
          in our <a href="/terms" style={{ color: "inherit" }}>Terms of Service</a>.
        </p>
      </Section>

      <Section title="Definitions and key terms">
        <ul style={{ paddingLeft: 20, lineHeight: 1.9 }}>
          <li><strong>Company / we / us / our:</strong> BrickForgerAI.</li>
          <li><strong>Country:</strong> BrickForgerAI is based in the United Kingdom.</li>
          <li><strong>Device:</strong> any internet-connected device (phone, tablet, computer) used to access the Service.</li>
          <li><strong>IP address:</strong> a number assigned to your device that can be used to estimate its general location.</li>
          <li><strong>Personal Data:</strong> any information that, alone or combined with other information, identifies you.</li>
          <li><strong>Service:</strong> the BrickForgerAI website and the generation service it provides.</li>
          <li><strong>Website:</strong> <a href="https://brickforgerai.com/" style={{ color: "inherit" }}>https://brickforgerai.com/</a>.</li>
          <li><strong>You:</strong> the person registered with BrickForgerAI to use the Service.</li>
        </ul>
      </Section>

      <Section title="What information do we collect?">
        <p>Directly from you, when you register or use the Service:</p>
        <ul style={{ paddingLeft: 20, lineHeight: 1.8 }}>
          <li>Email address</li>
          <li>Password (bcrypt-hashed before storage — we never store or see it in plain text)</li>
        </ul>
        <p style={{ marginTop: 14 }}>
          As part of actually using the Service, we also store the text prompts you submit and
          the images, 3D meshes, and brick models generated from them, so you can revisit and
          re-download your own results.
        </p>
      </Section>

      <Section title="How do we use the information we collect?">
        <ul style={{ paddingLeft: 20, lineHeight: 1.8 }}>
          <li>To provide the Service — generating and storing your models, and authenticating your account</li>
          <li>To respond to support requests you send us</li>
          <li>To improve the Service based on how it&apos;s actually used</li>
          <li>To enforce our Terms of Service, including our content restrictions</li>
        </ul>
        <p style={{ marginTop: 14 }}>
          We do not send marketing emails or newsletters, and we do not use your email address for
          advertising or audience-targeting purposes of any kind.
        </p>
      </Section>

      <Section title="Do we share the information we collect with third parties?">
        <p>
          We do not sell your personal information, and we do not share it with advertisers,
          marketing partners, or ad networks — we don&apos;t have any. We do share the minimum
          necessary data with the service providers that make the Service work:
        </p>
        <ul style={{ paddingLeft: 20, lineHeight: 1.8 }}>
          <li>Your prompt is sent to OpenAI to generate a reference image</li>
          <li>That image is sent to our 3D-generation provider (fal.ai, running TRELLIS 2) to produce a mesh</li>
          <li>Railway hosts our servers, database, and job queue</li>
          <li>Cloudflare R2 stores your generated files</li>
          <li>Sentry receives error/crash reports to help us fix bugs — this can include request metadata such as your IP address, but never your password</li>
        </ul>
        <p style={{ marginTop: 14 }}>
          We may also disclose information where required to comply with a legal obligation, court
          order, or valid request from a public authority, or to protect the rights, property, or
          safety of BrickForgerAI, our users, or the public. If BrickForgerAI is ever acquired or
          merged with another company, your information may be transferred as part of that deal,
          subject to this Policy.
        </p>
      </Section>

      <Section title="How do we protect your information?">
        <p>
          We use reasonable technical and organizational measures to protect your information,
          including encrypted connections (HTTPS/TLS) and hashed password storage. No method of
          transmission or storage is 100% secure, and we cannot guarantee absolute security of any
          information you send us.
        </p>
      </Section>

      <Section title="Could my information be transferred to other countries?">
        <p>
          BrickForgerAI is based in the United Kingdom, but the service providers listed above may
          process or host information outside the UK. By using the Service, you consent to this
          transfer to the extent permitted by applicable law.
        </p>
      </Section>

      <Section title="How long do we keep your information?">
        <p>
          We keep your account and generated-model data for as long as your account is active. If
          you ask us to delete your account (see below), we&apos;ll remove your personal data
          within 30 days, except where we&apos;re required to keep something longer for legal
          reasons. Because this is an early-stage product without a fully built-out data
          pipeline yet, some backups may take longer to fully clear than our live systems.
        </p>
      </Section>

      <Section title="Can I update, correct, or delete my information?">
        <p>
          Yes — contact us at the email below to update your account details or request deletion
          of your personal data. There isn&apos;t a self-service &ldquo;delete my account&rdquo;
          button in the product yet, so this is currently handled manually on request; we aim to
          action deletion requests within 30 days.
        </p>
      </Section>

      <Section title="Tracking technologies">
        <p>
          We do not use cookies. The Service uses your browser&apos;s <strong>local storage</strong>{" "}
          to keep you signed in and remember your preferences (like light/dark mode and your last
          build-size choice) — this data stays on your device and is never included in a request
          header the way a cookie would be.
        </p>
      </Section>

      <Section title="Kids' privacy">
        <p>
          BrickForgerAI is not directed at, and we do not knowingly collect personal information
          from, anyone under the age of 13. If you believe a child has provided us with personal
          data, please contact us and we&apos;ll remove it.
        </p>
      </Section>

      <Section title="Links to other websites">
        <p>
          The Service may link to other websites not operated by us (for example, BrickLink or
          Studio). We&apos;re not responsible for the content or privacy practices of any
          third-party site, and this Policy doesn&apos;t apply once you leave our Service.
        </p>
      </Section>

      <Section title="Information about the General Data Protection Regulation (GDPR)">
        <p>
          If you&apos;re in the UK or the European Economic Area, the GDPR (and UK GDPR) gives you
          rights over your personal data, including the right to access, correct, delete, restrict,
          or port the data we hold about you. You can exercise any of these rights by contacting us
          at the email below — we&apos;ll respond within one month. We do not sell personal data,
          and we only collect what&apos;s needed to provide the Service.
        </p>
      </Section>

      <Section title="California residents (CCPA)">
        <p>
          If you&apos;re a California resident, you have the right to know what categories of
          personal information we collect and why (see above), the right to request deletion of
          your account and associated data, and the right to equal service regardless of whether
          you exercise these rights. We do not sell personal information. To exercise any of these
          rights, contact us below — we&apos;ll respond within one month.
        </p>
      </Section>

      <Section title="Changes to this Privacy Policy">
        <p>
          We may update this Policy as the Service changes. We&apos;ll post the updated version
          here with a new &ldquo;last updated&rdquo; date; continued use of the Service after a
          change means you accept the update. If you don&apos;t agree with an update, you can stop
          using the Service and contact us to request account deletion.
        </p>
      </Section>

      <Section title="Contact us">
        <p>
          Questions about this Policy, or a request to access, correct, or delete your data? Email{" "}
          <a href="mailto:help@brickforgerai.com" style={{ color: "inherit" }}>
            help@brickforgerai.com
          </a>
          .
        </p>
      </Section>
    </StaticPage>
  );
}
