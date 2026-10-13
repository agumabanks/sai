<?php

namespace Tests\Feature\SanaaDoctor;

use App\Console\Commands\SanaaDoctor\PollAppsCommand;
use App\Services\SanaaDoctor\GroqDiagnoser;
use App\Services\SanaaDoctor\HealDispatcher;
use App\Services\SanaaDoctor\HealthScorer;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class SanaaDoctorTest extends TestCase
{
    use RefreshDatabase;

    public function test_health_scorer_returns_correct_score_and_status(): void
    {
        $scorer = new HealthScorer;

        // Perfect health
        $result = $scorer->score([
            'queue_depth' => 10,
            'failed_jobs_1h' => 0,
            'db_latency_ms' => 100,
            'redis_ok' => true,
            'error_rate_1h' => 0,
            'last_order_at' => now()->subMinutes(10)->toDateTimeString(),
            'disk_free_percent' => 50,
        ], [
            'queue_depth_max' => 50,
            'failed_jobs_1h_max' => 5,
            'db_latency_ms_max' => 300,
            'error_rate_1h_max' => 5.0,
            'last_order_stale_minutes' => 60,
        ]);

        $this->assertEquals(100, $result['score']);
        $this->assertEquals('healthy', $result['status']);
        $this->assertEmpty($result['flags']);

        // Degraded: queue depth + failed jobs
        $result = $scorer->score([
            'queue_depth' => 60,
            'failed_jobs_1h' => 8,
            'db_latency_ms' => 100,
            'redis_ok' => true,
            'error_rate_1h' => 0,
            'last_order_at' => now()->subMinutes(10)->toDateTimeString(),
            'disk_free_percent' => 50,
        ], [
            'queue_depth_max' => 50,
            'failed_jobs_1h_max' => 5,
            'db_latency_ms_max' => 300,
            'error_rate_1h_max' => 5.0,
            'last_order_stale_minutes' => 60,
        ]);

        $this->assertEquals(70, $result['score']);
        $this->assertEquals('degraded', $result['status']);
        $this->assertContains('high queue depth', $result['flags']);
        $this->assertContains('high failed jobs', $result['flags']);

        // Critical: redis down + critical disk space
        $result = $scorer->score([
            'queue_depth' => 0,
            'failed_jobs_1h' => 0,
            'db_latency_ms' => 100,
            'redis_ok' => false,
            'error_rate_1h' => 0,
            'last_order_at' => now()->subMinutes(10)->toDateTimeString(),
            'disk_free_percent' => 3,
        ], [
            'queue_depth_max' => 50,
            'failed_jobs_1h_max' => 5,
            'db_latency_ms_max' => 300,
            'error_rate_1h_max' => 5.0,
            'last_order_stale_minutes' => 60,
        ]);

        $this->assertEquals(35, $result['score']);
        $this->assertEquals('critical', $result['status']);
        $this->assertContains('redis down', $result['flags']);
        $this->assertContains('critical disk space', $result['flags']);
    }

    public function test_poll_apps_command_handles_unreachable_app_gracefully(): void
    {
        config()->set('sanaa_apps.apps', [
            'fake_app' => [
                'key' => 'fake_app',
                'name' => 'Fake App',
                'health_url' => 'http://localhost:59999/api/health',
                'heal_url' => null,
                'api_secret' => 'secret',
                'tenant' => null,
                'thresholds' => [],
            ],
        ]);

        Http::fake([
            'http://localhost:59999/api/health' => Http::response(null, 500),
        ]);

        $this->artisan(PollAppsCommand::class)
            ->assertSuccessful();

        $this->assertDatabaseHas('sanaa_health_log', [
            'app' => 'fake_app',
            'score' => 0,
            'status' => 'critical',
        ]);
    }

    public function test_groq_diagnoser_falls_back_when_api_is_down(): void
    {
        Http::fake([
            'https://api.groq.com/*' => Http::response(null, 503),
        ]);

        $diagnoser = new GroqDiagnoser;
        $result = $diagnoser->diagnose('test_app', [], ['redis down']);

        $this->assertArrayHasKey('diagnosis', $result);
        $this->assertArrayHasKey('recommended_action', $result);
        $this->assertArrayHasKey('trigger_heal', $result);
        $this->assertArrayHasKey('urgency', $result);
        $this->assertTrue($result['trigger_heal']);
        $this->assertEquals('CRITICAL', $result['urgency']);
    }

    public function test_heal_dispatcher_skips_heal_when_url_is_null(): void
    {
        $dispatcher = new HealDispatcher;

        $result = $dispatcher->dispatch(
            [
                'heal_url' => null,
                'api_secret' => 'secret',
            ],
            ['high queue depth'],
            'Queue is backed up.',
            'Restart queue workers.'
        );

        $this->assertEquals('alert_sent', $result['action_taken']);
        $this->assertNull($result['heal_response']);
    }
}
