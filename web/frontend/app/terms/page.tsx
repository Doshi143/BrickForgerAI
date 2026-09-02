import StaticPage, { Section } from "@/components/StaticPage";

export default function TermsPage() {
  return (
    <StaticPage title="Terms of Service" subtitle="Last updated August 7th, 2026">
      <Section title="General terms">
        <p>
          By accessing or using BrickForgerAI (&ldquo;we,&rdquo; &ldquo;us,&rdquo; the
          &ldquo;Service&rdquo;), you agree to be bound by these Terms of Service. If you do not
          agree, please do not use the Service. If you violate these Terms, we reserve the right
          to suspend or terminate your account without notice.
        </p>
      </Section>

      <Section title="What this service does">
        <p>
          BrickForgerAI turns a text description into a 3D model built from real,
          LEGO-compatible brick, plate, tile, and slope shapes, exported as an{" "}
          <code>.ldr</code> file.
        </p>
      </Section>

      <Section title="Trademark disclaimer">
        <p>
          BrickForgerAI is not affiliated with, endorsed by, or sponsored by the LEGO Group,
          BrickLink, or Studio. &ldquo;LEGO&rdquo;, &ldquo;BrickLink&rdquo;, and
          &ldquo;Studio&rdquo; are trademarks of their respective owners. We reference BrickLink
          and Studio only to describe how a generated model&apos;s <code>.ldr</code> file can be
          opened and its parts purchased - not to suggest any partnership. Part geometry is drawn
          from the LDraw parts library, licensed under CCAL 2.0.
        </p>
      </Section>

      <Section title="Your prompts and content">
        <p>
          Generate original designs - don&apos;t prompt for copyrighted characters, logos, or
          existing commercial LEGO sets. Content that appears to target a specific copyrighted
          character or trademark may be refused or removed. You&apos;re responsible for what you
          type in and for how you use the resulting files.
        </p>
      </Section>

      <Section title="Restrictions">
        <p>You agree not to, and not to permit others to:</p>
        <ul style={{ paddingLeft: 20, lineHeight: 1.8 }}>
          <li>Resell, sublicense, or commercially redistribute access to the Service itself</li>
          <li>Reverse-engineer, decompile, or attempt to extract the underlying pipeline or models</li>
          <li>Remove or obscure any copyright, trademark, or attribution notice</li>
        </ul>
      </Section>

      <Section title="Credits and plans">
        <p>
          The Free plan includes 5 model generations a month. Builder includes 12, with
          instructions unlocks included free on every generation, for £9/month. Master Builder
          includes 30, also with instructions included, for £20/month. Unused credits do not roll
          over between months. Any signed-in user, on any plan, can also buy a one-off top-up of
          +5 credits for £6, added on top of their current balance without affecting their
          monthly plan allowance.
        </p>
      </Section>

      <Section title="Payment">
        <p>
          Registering for a recurring plan, or buying a top-up or a one-time instructions unlock,
          means you agree to pay the fees shown at checkout. All payments are handled entirely by
          Stripe, our payment processor - we never see, receive, or store your card number or
          other payment details ourselves, only what Stripe tells us afterward (that a payment
          succeeded, and which plan or product it was for). Stripe&apos;s own terms govern your
          rights and liabilities as a payment-method holder. We reserve the right to change
          prices, with notice posted on the Service or sent to your account email before the
          change takes effect for existing subscribers.
        </p>
        <p style={{ marginTop: 14 }}>
          A subscription renews automatically each month until you cancel. You can cancel or
          change plans at any time by contacting us at the email below; a cancellation takes
          effect at the end of your current billing period, and we don&apos;t charge a
          cancellation fee.
        </p>
      </Section>

      <Section title="Refunds">
        <p>
          If you&apos;re not satisfied with a purchase, contact us and we&apos;ll work through it
          with you directly.
        </p>
      </Section>

      <Section title="Your suggestions">
        <p>
          Any feedback, ideas, or suggestions you send us about the Service may be used by us
          freely, without any obligation to credit or compensate you.
        </p>
      </Section>

      <Section title="Tracking technologies">
        <p>
          We do not use cookies. See our{" "}
          <a href="/privacy" style={{ color: "inherit" }}>Privacy Policy</a> for the (very short)
          list of tracking technology we do use.
        </p>
      </Section>

      <Section title="Modifications, updates, and availability">
        <p>
          We may modify, suspend, or discontinue the Service or any feature of it at any time,
          with or without notice, and without liability to you. We may also release updates,
          patches, or changes to how the Service works; continued use after an update means
          you&apos;re bound by these Terms as applied to the updated Service.
        </p>
      </Section>

      <Section title="Third-party services">
        <p>
          The Service relies on third-party providers (see our{" "}
          <a href="/privacy" style={{ color: "inherit" }}>Privacy Policy</a>) and may link to
          other websites. We&apos;re not responsible for the accuracy, availability, or content
          of any third-party service or website, and you use them at your own risk.
        </p>
      </Section>

      <Section title="Term and termination">
        <p>
          This Agreement stays in effect until terminated by you or us. We may suspend or
          terminate your access at any time, for any reason, including a violation of these
          Terms. You can stop using the Service at any time; you don&apos;t need to tell us.
        </p>
      </Section>

      <Section title="Copyright infringement notice">
        <p>
          If you believe content on the Service infringes your copyright, contact us with: (a) a
          signature of the copyright owner or their authorized agent; (b) identification of the
          material claimed to be infringing; (c) your contact information; (d) a good-faith
          statement that the use is unauthorized; and (e) a statement, under penalty of perjury,
          that the notice is accurate and you&apos;re authorized to act on the owner&apos;s
          behalf.
        </p>
      </Section>

      <Section title="No warranty and model accuracy">
        <p>
          The Service is provided &ldquo;as is&rdquo; and &ldquo;as available,&rdquo; without
          warranties of any kind, express or implied, including merchantability, fitness for a
          particular purpose, and non-infringement. Generated models are produced automatically
          and are not guaranteed to be physically buildable, structurally sound, or free of
          errors.
        </p>
        <p style={{ marginTop: 14 }}>
          Specifically on structural stability: we cannot guarantee that any given generated
          model will be very physically stable - that depends heavily on what you asked for and
          how thin or overhanging the resulting shape is. What we can say is that the vast
          majority of generated models come out with 100% connectivity and few flagged issues on
          BrickLink Studio&apos;s own stability checker, thanks to a built-in support-structure
          algorithm that automatically detects and braces weak points during generation. Always
          check a generated model in BrickLink Studio (or by hand) before ordering parts or
          building.
        </p>
      </Section>

      <Section title="Indemnification">
        <p>
          You agree to indemnify and hold BrickForgerAI harmless from any claim arising from your
          use of the Service, your violation of these Terms, or your violation of any third
          party&apos;s rights.
        </p>
      </Section>

      <Section title="Limitation of liability">
        <p>
          To the maximum extent permitted by law, BrickForgerAI&apos;s total liability under
          these Terms is limited to the amount you actually paid us in the preceding 12 months,
          and we won&apos;t be liable for indirect, incidental, or consequential damages
          (including lost profits or lost data) arising from your use of the Service. Some
          jurisdictions don&apos;t allow these limitations, so they may not apply to you.
        </p>
      </Section>

      <Section title="Dispute resolution">
        <p>
          If a dispute arises, please contact us first at{" "}
          <a href="mailto:help@brickforgerai.com" style={{ color: "inherit" }}>
            help@brickforgerai.com
          </a>{" "}
          so we can try to resolve it informally. These Terms are governed by the laws of the
          United Kingdom, and any dispute not resolved informally is subject to the exclusive
          jurisdiction of the courts of the United Kingdom.
        </p>
      </Section>

      <Section title="Intellectual property">
        <p>
          The Service and its content (excluding the models you generate and the third-party
          brick-part geometry it&apos;s built from) are owned by BrickForgerAI and protected by
          UK and international intellectual property law. You may not copy, modify, or
          redistribute the Service itself without our prior written permission.
        </p>
      </Section>

      <Section title="Severability and entire agreement">
        <p>
          If any provision of these Terms is found unenforceable, the rest remains in full
          force. These Terms, together with our{" "}
          <a href="/privacy" style={{ color: "inherit" }}>Privacy Policy</a>, are the entire
          agreement between you and BrickForgerAI regarding the Service.
        </p>
      </Section>

      <Section title="Changes to these terms">
        <p>
          We may update these Terms as the Service changes. Material changes will be posted here
          with an updated date; continued use of the Service after a change means you accept it.
          This is an early-stage product, so terms may change more often than a mature product&apos;s
          would.
        </p>
      </Section>

      <Section title="Contact us">
        <p>
          Questions about these Terms? Email{" "}
          <a href="mailto:help@brickforgerai.com" style={{ color: "inherit" }}>
            help@brickforgerai.com
          </a>
          .
        </p>
      </Section>
    </StaticPage>
  );
}
