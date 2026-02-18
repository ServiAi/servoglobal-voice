import { MetadataRoute } from 'next';
import { locales } from '@/i18n';

const BASE_URL = 'https://www.serviglobal-ia.com';

export default function sitemap(): MetadataRoute.Sitemap {
  const sitemapEntries: MetadataRoute.Sitemap = [];

  // Home page for each locale
  for (const locale of locales) {
    sitemapEntries.push({
      url: `${BASE_URL}/${locale}`,
      lastModified: new Date(),
      changeFrequency: 'weekly',
      priority: 1,
    });
  }

  // Root URL (redirects to default locale usually, but good to have)
  sitemapEntries.push({
    url: `${BASE_URL}/`,
    lastModified: new Date(),
    changeFrequency: 'weekly',
    priority: 1,
  });

  return sitemapEntries;
}
