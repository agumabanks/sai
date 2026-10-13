<?php

namespace Tests\Feature\SanaaDoctor;

use App\Models\SanaaHealthLog;
use App\Models\User;
use App\Support\SanaaEcosystem;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;
use Tests\TestCase;

class EcosystemHealTest extends TestCase
{
    use RefreshDatabase;

    public function test_manual_heal_uses_scored_flags_not_raw_signal_keys(): void
    {
        config()->set('sanaa_apps.apps', [
            'antigravity' => [
                'key' => 'antigravity',
                'name' => 'Antigravity AI',
                'health_url' => 'https://ai.sanaa.co/health',
                'heal_url' => 'https://ai.sanaa.co/health/heal',
                'api_secret' => 'test-secret',
                'thresholds' => [
                    'queue_depth_max' => 50,
                    'failed_jobs_1h_max' => 5,
                    'db_latency_ms_max' => 300,
                    'error_rate_1h_max' => 5.0,
                ],
            ],
        ]);

        SanaaHealthLog::query()->create([
            'id' => (string) Str::uuid(),
            'app' => 'antigravity',
            'tenant' => null,
            'signals' => [
                'queue_depth' => 99,
                'failed_jobs_1h' => 0,
                'db_latency_ms' => 10,
                'redis_ok' => true,
            ],
            'score' => 90,
            'status' => 'degraded',
            'action_taken' => 'none',
        ]);

        Http::fake([
            'https://ai.sanaa.co/health/heal' => Http::response([
                'healed' => true,
                'actions_taken' => ['queue:restart'],
            ], 200),
            'https://ai.sanaa.co/health' => Http::response(['signals' => ['queue_depth' => 0]], 200),
        ]);

        $result = SanaaEcosystem::healApp('antigravity');

        $this->assertTrue($result['success']);
        $this->assertTrue($result['healed']);
        $this->assertContains('high queue depth', $result['flags']);

        Http::assertSent(function ($request) {
            return $request->url() === 'https://ai.sanaa.co/health/heal'
                && in_array('high queue depth', $request['flags'] ?? [], true);
        });
    }

    public function test_unreachable_app_returns_actionable_error(): void
    {
        config()->set('sanaa_apps.apps', [
            'baraka24' => [
                'key' => 'baraka24',
                'name' => 'Baraka 24',
                'health_url' => 'https://baraka.sanaa.co/api/health',
                'heal_url' => 'https://baraka.sanaa.co/api/heal',
                'api_secret' => 'secret',
                'thresholds' => [],
            ],
        ]);

        SanaaHealthLog::query()->create([
            'id' => (string) Str::uuid(),
            'app' => 'baraka24',
            'tenant' => null,
            'signals' => [],
            'score' => 0,
            'status' => 'critical',
            'action_taken' => 'alert_sent',
        ]);

        $result = SanaaEcosystem::healApp('baraka24');

        $this->assertFalse($result['success']);
        $this->assertStringContainsString('unreachable', strtolower($result['error']));
    }

    public function test_heal_route_requires_auth_and_accepts_valid_csrf(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)
            ->post('/os/ecosystem/unknown/heal')
            ->assertJson(['success' => false, 'error' => 'Unknown app key']);
    }
}
