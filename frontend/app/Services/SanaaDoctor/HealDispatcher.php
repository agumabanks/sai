<?php

namespace App\Services\SanaaDoctor;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class HealDispatcher
{
    /**
     * Dispatch a heal webhook to the target app if configured.
     *
     * @param  array<string, mixed>  $appConfig
     * @param  array<int, string>  $flags
     * @return array{action_taken: string, heal_response: array<string, mixed>|null}
     */
    public function dispatch(array $appConfig, array $flags, string $diagnosis, string $recommendedAction): array
    {
        $healUrl = $appConfig['heal_url'] ?? null;
        $apiSecret = $appConfig['api_secret'] ?? null;

        if (empty($healUrl)) {
            return [
                'action_taken' => 'alert_sent',
                'heal_response' => null,
            ];
        }

        $bearerToken = ! empty($apiSecret) ? $apiSecret : env('SANAA_DOCTOR_SECRET', '');

        try {
            $response = Http::withHeaders([
                'Authorization' => 'Bearer '.$bearerToken,
                'Accept' => 'application/json',
                'Content-Type' => 'application/json',
            ])
                ->timeout(15)
                ->post($healUrl, [
                    'flags' => $flags,
                    'diagnosis' => $diagnosis,
                    'recommended_action' => $recommendedAction,
                ]);

            $healResponse = $response->json() ?? ['raw' => $response->body()];

            if (! $response->successful()) {
                Log::warning('HealDispatcher webhook failed', [
                    'url' => $healUrl,
                    'status' => $response->status(),
                    'response' => $healResponse,
                ]);

                return [
                    'action_taken' => 'alert_sent',
                    'heal_response' => array_merge(is_array($healResponse) ? $healResponse : ['raw' => $healResponse], [
                        'http_status' => $response->status(),
                        'error' => 'Heal webhook returned HTTP '.$response->status(),
                    ]),
                ];
            }

            return [
                'action_taken' => 'heal_triggered',
                'heal_response' => array_merge(is_array($healResponse) ? $healResponse : ['raw' => $healResponse], [
                    'http_status' => $response->status(),
                ]),
            ];
        } catch (\Exception $e) {
            Log::error('HealDispatcher exception', ['url' => $healUrl, 'error' => $e->getMessage()]);

            return [
                'action_taken' => 'alert_sent',
                'heal_response' => ['error' => $e->getMessage()],
            ];
        }
    }
}
