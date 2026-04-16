import { WithContext, Organization, SoftwareApplication } from 'schema-dts';

export function JsonLd() {
  const organizationSchema: WithContext<Organization> = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: 'ServiGlobal · IA',
    url: 'https://www.serviglobal-ia.com',
    logo: 'https://www.serviglobal-ia.com/logo.png',
    description: 'Guided implementation of Servi-IA for scheduling, lead capture, and automated service.',
    contactPoint: {
      '@type': 'ContactPoint',
      telephone: '+1-555-010-9999',
      contactType: 'sales',
      areaServed: ['US', 'ES', 'MX', 'CO'],
      availableLanguage: ['en', 'es']
    },
    sameAs: [
      'https://www.linkedin.com/company/serviglobal-ai',
      'https://twitter.com/serviglobal_ai'
    ]
  };

  const softwareSchema: WithContext<SoftwareApplication> = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'Servi-IA',
    applicationCategory: 'BusinessApplication',
    operatingSystem: 'Cloud',
    offers: {
      '@type': 'Offer',
      price: '510',
      priceCurrency: 'USD',
      description: 'Servi-IA Web Conversion monthly service operation with guided implementation'
    }
  };

  return (
    <section>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationSchema) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareSchema) }}
      />
    </section>
  );
}

