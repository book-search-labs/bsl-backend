# U-0117 — Web User: Checkout UI (Select address/delivery/billing)

## Goal
Please complete the checkout before order creation.

## Why
- Steps to establish “Order Information” that you need to enter before order creation/payment integration
- Business issues (address/shipping/research) Most of this happens here

## Scope
### 1) Checkout step configuration
- Step 1: Shipping
- Step 2: Shipping options (with shipping method/promotional option)
- Step 3: Select payment method (card/simple payment, etc. — MVP is based on “PG”.

### 2) Address UX
- Shipping Area / Add New Shipping Area
- Set up the shipping location
- Form validation (required/phone number format)

### 3) Order Summary
- Terms and Conditions for Overnight Stay
- Click “Order” button   TBD  

### 4) Error processing
- Re-confirmation Modal when changing the lack of inventory/price
- Copyright (c) SHINSEGAE LANGUAGE SCHOOL. All Rights Reserved.

## Non-goals
- Membership/Coupon/Promotion Complex Logic

## DoD
- Checkout to address/delivery/delivery checkout to order creation
- validation and error handling

## Interfaces
- New  TBD   (Term Data)
- New  TBD   (Order creation)
- (Option)   TBD  

## Files (example)
- `web-user/src/pages/checkout/CheckoutPage.tsx`
- `web-user/src/components/checkout/AddressForm.tsx`
- `web-user/src/components/checkout/PaymentMethodSelect.tsx`
- `web-user/src/api/checkout.ts`

## Codex Prompt
Implement Checkout UI:
- Multi-section page (address, shipping, payment method, order summary).
- Validate forms, handle stock/price change warnings, and create order on submit.
