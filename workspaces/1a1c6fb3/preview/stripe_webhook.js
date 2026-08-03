// Installation Instructions:
// 1. First, install Stripe using npm or yarn.
//    ```
//    npm install stripe
//    # or
//    yarn add stripe
// 2. Then, create a new file named `webhook.js` in the root of your project.

const stripe = require('stripe')(YOUR_STRIPE_PUBLISHABLE_KEY);

// Example usage:
stripe.webhook({
  url: 'https://your-stripe-webhook-url',
  secretKey: YOUR_STRIPE_SECRET_KEY,
});

// Working demo component:
// Replace `YOUR_STRIPE_PUBLISHABLE_KEY` with your actual Stripe publishable key.
// Replace `YOUR_STRIPE_SECRET_KEY` with your actual Stripe secret key.

// Example usage in a working demo component:
import { webhook } from './webhook.js';

const url = 'https://your-stripe-webhook-url';
const secretKey = YOUR_STRIPE_SECRET_KEY;

stripe.webhook({
  url,
  secretKey,
});