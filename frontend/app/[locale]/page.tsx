import { Header } from '@/components/shared/Header';
import { Hero } from '@/components/landing/Hero';
import { TrustStrip } from '@/components/landing/TrustStrip';
import { UseCases } from '@/components/landing/UseCases';
import { Benefits } from '@/components/landing/Benefits';
import { ROIStory } from '@/components/landing/ROIStory';
import { Process } from '@/components/landing/Process';
import { Integrations } from '@/components/landing/Integrations';
import { Pricing } from '@/components/landing/Pricing';
import { WhyUs } from '@/components/landing/WhyUs';
import { FAQ } from '@/components/landing/FAQ';
import { VoiceDemo } from '@/components/landing/VoiceDemo';
import { Booking } from '@/components/landing/Booking';

import { FloatingCTA } from '@/components/shared/FloatingCTA';
import { BrandSpotlightScope } from '@/components/ui/spotlight-card';

export default function Home() {
  return (
    <BrandSpotlightScope className="flex min-h-screen flex-col">
      <Header />
      <Hero />
      <TrustStrip />
      <UseCases />
      <Benefits />
      <ROIStory />
      <Process />
      <Integrations />
      <Pricing />
      <WhyUs />
      <FAQ />
      <VoiceDemo />
      <Booking />

      <FloatingCTA />
    </BrandSpotlightScope>
  );
}
