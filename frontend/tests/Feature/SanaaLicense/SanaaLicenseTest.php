<?php

namespace Tests\Feature\SanaaLicense;

use App\Console\Commands\SanaaLicense\CheckSubscriptionsCommand;
use App\Models\SanaaLicensePlan;
use App\Models\SanaaLicenseTenant;
use App\Services\SanaaLicense\LicensePaymentService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class SanaaLicenseTest extends TestCase
{
    use RefreshDatabase;

    protected array $tenantTokens = [];

    protected function createTenant(array $overrides = []): SanaaLicenseTenant
    {
        $plan = SanaaLicensePlan::create([
            'id' => (string) \Illuminate\Support\Str::uuid(),
            'name' => 'Test Plan',
            'price_ugx' => 100000,
            'billing_cycle_days' => 30,
            'features' => ['loans', 'savings'],
            'is_active' => true,
        ]);

        $tenant = new SanaaLicenseTenant;
        $tenant->id = (string) \Illuminate\Support\Str::uuid();
        $tenant->tenant_key = $overrides['tenant_key'] ?? 'test_tenant';
        $tenant->tenant_name = $overrides['tenant_name'] ?? 'Test Tenant';
        $tenant->contact_name = 'Test Contact';
        $tenant->contact_phone = '0706272481';
        $tenant->plan_id = $plan->id;
        $tenant->status = $overrides['status'] ?? 'active';
        $tenant->subscription_starts_at = now()->subDays(10);
        $tenant->subscription_ends_at = $overrides['subscription_ends_at'] ?? now()->addDays(10);
        $tenant->trial_ends_at = $overrides['trial_ends_at'] ?? null;
        $tenant->grace_period_days = 7;
        $tenant->kill_switch_active = $overrides['kill_switch_active'] ?? false;
        $token = $tenant->generateLicenseToken();
        $tenant->save();

        $this->tenantTokens[$tenant->id] = $token;

        return $tenant;
    }

    public function test_license_check_returns_allowed_true_for_active_tenant(): void
    {
        $tenant = $this->createTenant();

        $response = $this->postJson('/api/license/check', [
            'tenant_key' => $tenant->tenant_key,
            'license_token' => $this->tenantTokens[$tenant->id],
        ]);

        $response->assertOk()
            ->assertJsonPath('allowed', true)
            ->assertJsonPath('status', 'active');
    }

    public function test_license_check_returns_allowed_false_for_suspended_tenant(): void
    {
        $tenant = $this->createTenant([
            'status' => 'suspended',
            'subscription_ends_at' => now()->subDays(5),
            'kill_switch_active' => true,
        ]);

        $response = $this->postJson('/api/license/check', [
            'tenant_key' => $tenant->tenant_key,
            'license_token' => $this->tenantTokens[$tenant->id],
        ]);

        $response->assertOk()
            ->assertJsonPath('allowed', false)
            ->assertJsonPath('status', 'suspended');
    }

    public function test_license_check_returns_allowed_false_when_kill_switch_active(): void
    {
        $tenant = $this->createTenant([
            'subscription_ends_at' => now()->addDays(10),
            'kill_switch_active' => true,
        ]);

        $response = $this->postJson('/api/license/check', [
            'tenant_key' => $tenant->tenant_key,
            'license_token' => $this->tenantTokens[$tenant->id],
        ]);

        $response->assertOk()
            ->assertJsonPath('allowed', false)
            ->assertJsonPath('kill_switch_active', true);
    }

    public function test_warning_message_appears_when_five_days_until_expiry(): void
    {
        $tenant = $this->createTenant([
            'subscription_ends_at' => now()->addDays(5)->startOfDay(),
        ]);

        $response = $this->postJson('/api/license/check', [
            'tenant_key' => $tenant->tenant_key,
            'license_token' => $this->tenantTokens[$tenant->id],
        ]);

        $response->assertOk()
            ->assertJsonPath('allowed', true)
            ->assertJsonPath('days_until_expiry', 5)
            ->assertJsonFragment(['warning' => 'Your subscription expires in 5 days. Contact Sanaa Finance to renew.']);
    }

    public function test_check_subscriptions_command_moves_active_to_grace(): void
    {
        $tenant = $this->createTenant([
            'status' => 'active',
            'subscription_ends_at' => now()->subDay(),
        ]);

        $this->artisan(CheckSubscriptionsCommand::class)->assertSuccessful();

        $tenant->refresh();
        $this->assertEquals('grace', $tenant->status);
        $this->assertDatabaseHas('sanaa_license_events', [
            'tenant_id' => $tenant->id,
            'event_type' => 'suspended',
            'triggered_by' => 'system',
        ]);
    }

    public function test_check_subscriptions_command_suspends_expired_grace_period(): void
    {
        $tenant = $this->createTenant([
            'status' => 'grace',
            'subscription_ends_at' => now()->subDays(10),
        ]);

        $this->artisan(CheckSubscriptionsCommand::class)->assertSuccessful();

        $tenant->refresh();
        $this->assertEquals('suspended', $tenant->status);
        $this->assertTrue($tenant->kill_switch_active);
        $this->assertDatabaseHas('sanaa_license_events', [
            'tenant_id' => $tenant->id,
            'event_type' => 'killed',
            'triggered_by' => 'system',
        ]);
    }

    public function test_payment_recording_extends_subscription(): void
    {
        $tenant = $this->createTenant([
            'status' => 'suspended',
            'subscription_ends_at' => now()->subDays(5),
            'kill_switch_active' => true,
        ]);

        $originalEndsAt = $tenant->subscription_ends_at->copy();

        LicensePaymentService::recordPayment(
            tenant: $tenant,
            amountUgx: 100000,
            paymentMethod: 'mobile_money',
            reference: 'TEST123',
            paidAt: now(),
            extendsByDays: 30,
            recordedBy: 'Admin User',
            notes: 'Test payment'
        );

        $tenant->refresh();
        $this->assertEquals('active', $tenant->status);
        $this->assertFalse($tenant->kill_switch_active);
        $this->assertTrue($tenant->subscription_ends_at->greaterThan($originalEndsAt));
        $this->assertDatabaseHas('sanaa_license_payments', [
            'tenant_id' => $tenant->id,
            'amount_ugx' => 100000,
            'payment_method' => 'mobile_money',
        ]);
    }

    public function test_wrong_license_token_returns_401_with_generic_error(): void
    {
        $tenant = $this->createTenant();

        $response = $this->postJson('/api/license/check', [
            'tenant_key' => $tenant->tenant_key,
            'license_token' => 'wrong-token-12345',
        ]);

        $response->assertUnauthorized()
            ->assertJsonFragment(['error' => 'Invalid credentials or request.']);
    }
}
