'use client';

import { EmailComposerModal } from '@/components/crm/email-composer/EmailComposerModal';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accessToken: string;
  leadId: string;
  onSent?: () => void;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
};

export function CrmSendEmailModal(props: Props) {
  return <EmailComposerModal {...props} />;
}
