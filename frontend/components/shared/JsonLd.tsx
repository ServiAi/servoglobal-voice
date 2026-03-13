import { WithContext, Organization, SoftwareApplication } from 'schema-dts';

export function JsonLd() {
  const organizationSchema: WithContext<Organization> = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: 'ServiGlobal · IA',
    url: 'https://www.serviglobal-ia.com',
    logo: 'https://www.serviglobal-ia.com/logo.png', // Replace with actual logo URL
    description: 'Implementación de agentes de voz con IA y soluciones omnicanal.',
    contactPoint: {
      '@type': 'ContactPoint',
      telephone: '+1-555-010-9999', // Replace with actual phone
      contactType: 'customer service',
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
    name: 'ServiGlobal IA Agent',
    applicationCategory: 'BusinessApplication',
    operatingSystem: 'Cloud',
    offers: {
      '@type': 'Offer',
      price: '299',
      priceCurrency: 'USD',
      description: 'Servi-IA Starter Plan'
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
