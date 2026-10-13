<?php

namespace App\Console\Commands\SanaaDoctor;

use App\Models\SanaaHealthLog;
use App\Services\SanaaDoctor\GroqDiagnoser;
use App\Services\SanaaDoctor\HealDispatcher;
use App\Services\SanaaDoctor\HealthScorer;
use App\Services\SanaaDoctor\WhatsAppNotifier;
use Illuminate\Console\Command;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\Pool;
use Illuminate\Support\Facades\Http;

class PollAppsCommand extends Command
{
    protected $signature = 'sanaa:doctor:poll {--tenant= : Only poll apps for this tenant}';

    protected $description = 'Poll all registered Sanaa apps for health status';

    public function handle(
        HealthScorer $scorer,
        GroqDiagnoser $diagnoser,
        HealDispatcher $healDispatcher,
        WhatsAppNotifier $notifier
    ): int {
        $apps = config('sanaa_apps.apps', []);

        $tenant = $this->option('tenant');
        if ($tenant) {
            $apps = array_filter($apps, fn ($app) => ($app['tenant'] ?? null) === $tenant);
        }

        if (empty($apps)) {
            $this->warn('No apps configured in sanaa_apps.php');

            return self::SUCCESS;
        }

        // Build concurrent requests
        $responses = Http::pool(function (Pool $pool) use ($apps) {
            foreach ($apps as $key => $app) {
                $secret = $app['api_secret'] ?? env('SANAA_DOCTOR_SECRET', '');
                $pool->as($key)
                    ->withHeaders([
                        'Authorization' => 'Bearer '.$secret,
                        'Accept' => 'application/json',
                    ])
                    ->timeout(10)
                    ->get($app['health_url']);
            }
        });

        $latestSummaries = [];

        foreach ($apps as $key => $app) {
            $this->info("Polling {$key}...");

            $response = $responses[$key] ?? null;

            $isFailed = $response instanceof ConnectionException
                || $response === null
                || (! $response instanceof ConnectionException && $response->failed());

            if ($isFailed) {
                $this->error("{$key} is unreachable.");

                $log = new SanaaHealthLog;
                $log->id = (string) \Illuminate\Support\Str::uuid();
                $log->app = $key;
                $log->tenant = $app['tenant'] ?? null;
                $log->signals = [];
                $log->score = 0;
                $log->status = 'critical';
                $log->groq_diagnosis = 'App unreachable — no response from health endpoint';
                $log->action_taken = 'alert_sent';
                $log->heal_response = null;
                $log->save();

                $notifier->sendCriticalAlert(
                    $app['name'] ?? $key,
                    ['diagnosis' => 'App unreachable — no response from health endpoint', 'recommended_action' => 'Check server and network connectivity immediately.'],
                    0,
                    ['unreachable']
                );

                $latestSummaries[$key] = [
                    'app' => $key,
                    'name' => $app['name'] ?? $key,
                    'score' => 0,
                    'status' => 'critical',
                ];

                continue;
            }

            $payload = $response->json();
            $signals = $payload['signals'] ?? [];
            $thresholds = $app['thresholds'] ?? [];

            $result = $scorer->score($signals, $thresholds);
            $score = $result['score'];
            $status = $result['status'];
            $flags = $result['flags'];

            $groqDiagnosis = null;
            $actionTaken = 'none';
            $healResponse = null;

            if ($score < 80) {
                $diagnosisResult = $diagnoser->diagnose($app['name'] ?? $key, $signals, $flags);
                $groqDiagnosis = $diagnosisResult['diagnosis'];

                $healResult = $healDispatcher->dispatch(
                    $app,
                    $flags,
                    $diagnosisResult['diagnosis'],
                    $diagnosisResult['recommended_action']
                );
                $actionTaken = $healResult['action_taken'];
                $healResponse = $healResult['heal_response'];

                if ($status === 'critical') {
                    $notifier->sendCriticalAlert(
                        $app['name'] ?? $key,
                        $diagnosisResult,
                        $score,
                        $flags
                    );
                }
            }

            $log = new SanaaHealthLog;
            $log->id = (string) \Illuminate\Support\Str::uuid();
            $log->app = $key;
            $log->tenant = $app['tenant'] ?? null;
            $log->signals = $signals;
            $log->score = $score;
            $log->status = $status;
            $log->groq_diagnosis = $groqDiagnosis;
            $log->action_taken = $actionTaken;
            $log->heal_response = $healResponse;
            $log->save();

            $latestSummaries[$key] = [
                'app' => $key,
                'name' => $app['name'] ?? $key,
                'score' => $score,
                'status' => $status,
            ];
        }

        // Cache the latest summaries for the daily digest to use later
        cache()->put('sanaa_doctor:latest_summaries', array_values($latestSummaries), now()->addDay());

        $this->info('Poll complete.');

        return self::SUCCESS;
    }
}
