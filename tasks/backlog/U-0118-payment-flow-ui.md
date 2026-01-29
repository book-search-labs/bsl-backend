# U-0118 — Web User: Payment flow UI (Profession/Proof/Proof)

## Goal
The payment process is completed in the user’s position “without broken”.
- Payment Start → Processing → Success/Proof → Retry / Return

## Why
- Payment is very common with error/relay/return click
- <# if ( data.meta.album ) { #>{{ data.meta.album }}<# } #> <# if ( data.meta.artist ) { #>{{ data.meta.artist }}<# } #>

## Scope
### 1) Payment start/stop screen
- “Payment processing” status (Loding + Information)
- Anti-slip (button disable)

### 2) Success screen
- Order number, payment amount, delivery time
- CTA

### 3) Failure screen
- Failure Ownership (Avaliable Range)
- Sashdo button (maintains the left light key)
- Select “Pay or Return to Order”

### 4) Sync status
- Page New and Back Support
- New  TBD   or   TBD  

## Non-goals
- The thread PG payment UI (card input form, etc.) is based on the integration method

## DoD
- We provide a clear UX for your payment success/fail/repair
- Anti-refund payment (premise processed with idempotency key such as rehabilitation)
- A new, fast-to-understand status is consistent

## Interfaces
- New  TBD   (Start payment)
- New  TBD  
- New  TBD   (Option)
- New  TBD   (Check Order Status)

## Files (example)
- `web-user/src/pages/payment/PaymentProcessingPage.tsx`
- `web-user/src/pages/payment/PaymentResultPage.tsx`
- `web-user/src/api/payment.ts`

## Codex Prompt
Implement Payment flow UI:
- Processing, success, failure pages with safe retry.
- Prevent double-submit, re-fetch state on refresh, and link back to order detail.
