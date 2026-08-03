import Stripe from 'stripe';

const stripe = new Stripe('YOUR_STRIPE_PUBLISHABLE_KEY', {
  apiVersion: '2023-11-15',
});

export default stripe;

// Example usage:
async function main() {
  try {
    const customer = await stripe.customers.create({
      email: 'example@example.com',
    });

    console.log(`Customer created successfully: ${customer.id}`);
  } catch (error) {
    console.error('Error creating customer:', error);
  }
}

main();