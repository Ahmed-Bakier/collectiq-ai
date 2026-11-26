import { useState } from "react";
import { Check, Copy, ExternalLink, LoaderCircle, Mail, MessageCircle, QrCode } from "lucide-react";
import { errorMessage } from "../../api/client";
import { usePaymentLink } from "../../api/hooks";
import { formatMoney } from "../../lib/format";

const SMALL_BUTTON =
  "inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-ink hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40";

/**
 * PayPal's own payment page for the invoice: a QR code, copy, and sharing through the
 * user's own apps (nothing is sent automatically). CollectIQ never shares any other link.
 */
export function PaymentLinkPanel({ invoiceId, message }: { invoiceId: string; message?: string | null }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const link = usePaymentLink(invoiceId, open);

  if (!open) {
    return (
      <button type="button" className={SMALL_BUTTON} onClick={() => setOpen(true)}>
        <QrCode className="size-3.5" aria-hidden />
        Payment link &amp; QR
      </button>
    );
  }
  if (link.isPending) {
    return (
      <p className="flex items-center gap-2 text-xs text-muted">
        <LoaderCircle className="size-3.5 animate-spin" aria-hidden />
        Getting the payment page from PayPal…
      </p>
    );
  }
  if (link.isError) {
    return (
      <p role="alert" className="text-xs text-danger">
        {errorMessage(link.error)}
      </p>
    );
  }

  const data = link.data;
  const number = data.invoice_number ?? data.invoice_id;
  const shareText = `${message ? `${message}\n\n` : ""}Pay securely with PayPal: ${data.pay_url}`;

  async function copyMessage() {
    try {
      await navigator.clipboard.writeText(shareText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section aria-label="Payment link and QR code" className="flex flex-wrap items-start gap-4 rounded-lg border border-slate-200 p-3">
      <img
        src={data.qr_svg_data_uri}
        alt={`QR code that opens PayPal's payment page for invoice ${number}`}
        width={132}
        height={132}
        className="rounded-md border border-slate-200 bg-white"
      />
      <div className="min-w-0 flex-1 space-y-2">
        <div>
          <p className="text-sm font-medium text-ink">Pay with PayPal: {formatMoney(data.amount_due, data.currency_code)}</p>
          <p className="text-xs text-muted">
            Scan or share. This opens PayPal&apos;s own page for invoice {number}; CollectIQ never shares any other link.
          </p>
        </div>
        <p className="truncate font-mono text-xs text-ink" title={data.pay_url}>
          {data.pay_url}
        </p>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={SMALL_BUTTON} onClick={copyMessage}>
            {copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
            {copied ? "Copied" : "Copy message + link"}
          </button>
          <a className={SMALL_BUTTON} href={`https://wa.me/?text=${encodeURIComponent(shareText)}`} target="_blank" rel="noreferrer">
            <MessageCircle className="size-3.5" aria-hidden />
            WhatsApp
          </a>
          <a
            className={SMALL_BUTTON}
            href={`mailto:?subject=${encodeURIComponent(`Invoice ${number}`)}&body=${encodeURIComponent(shareText)}`}
          >
            <Mail className="size-3.5" aria-hidden />
            Email
          </a>
          <a className={SMALL_BUTTON} href={data.pay_url} target="_blank" rel="noreferrer">
            <ExternalLink className="size-3.5" aria-hidden />
            Open in PayPal
          </a>
        </div>
      </div>
    </section>
  );
}
