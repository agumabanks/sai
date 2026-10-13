<?php

namespace App\Services\SanaaDoctor;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class GroqDiagnoser
{
    protected string $apiKey;

    protected string $model;

    public function __construct()
    {
        $this->apiKey = env('GROQ_API_KEY', '');
        $this->model = env('GROQ_MODEL', 'llama-3.3-70b-versatile');
    }

    /**
     * Diagnose health issues using Groq AI.
     *
     * @param  array<string, mixed>  $signals
     * @param  array<int, string>  $flags
     * @return array{diagnosis: string, recommended_action: string, trigger_heal: bool, urgency: string}
     */
    public function diagnose(string $app, array $signals, array $flags): array
    {
        if (empty($this->apiKey)) {
            return $this->fallback($flags);
        }

        $systemPrompt = <<<'PROMPT'
You are SanaaDoctor, the AI operations brain for Sanaa Co., a technology and cooperative ecosystem in Kampala, Uganda. You monitor the health of multiple production apps including Soko 24 (marketplace/ERP), Baraka 24 (logistics OS), Sanaa Finance (cooperative fintech), and fx.sanaa.co (FX platform).

You receive real-time health signals from these apps. Your job is to:
1. Diagnose what is likely wrong in plain English (2–3 sentences max)
2. Recommend the single most important action to take right now
3. Decide whether to trigger a /api/heal webhook or just alert the team
4. Assign urgency: LOW | MEDIUM | HIGH | CRITICAL

Respond ONLY in this JSON format — no markdown, no explanation outside the JSON:
{
  "diagnosis": "...",
  "recommended_action": "...",
  "trigger_heal": false,
  "urgency": "MEDIUM"
}
PROMPT;

        $userContent = sprintf(
            "App: %s\nSignals: %s\nFlags: %s",
            $app,
            json_encode($signals),
            json_encode($flags)
        );

        try {
            $response = Http::withHeaders([
                'Authorization' => 'Bearer '.$this->apiKey,
                'Content-Type' => 'application/json',
            ])
                ->timeout(30)
                ->post('https://api.groq.com/openai/v1/chat/completions', [
                    'model' => $this->model,
                    'messages' => [
                        ['role' => 'system', 'content' => $systemPrompt],
                        ['role' => 'user', 'content' => $userContent],
                    ],
                    'temperature' => 0.2,
                    'max_tokens' => 512,
                ]);

            if (! $response->successful()) {
                Log::warning('GroqDiagnoser API error', ['status' => $response->status(), 'body' => $response->body()]);

                return $this->fallback($flags);
            }

            $data = $response->json();
            $content = $data['choices'][0]['message']['content'] ?? '';

            // Clean up possible markdown code fences
            $content = preg_replace('/^```json\s*|\s*```$/m', '', trim($content));

            $parsed = json_decode($content, true);

            if (json_last_error() !== JSON_ERROR_NONE || ! is_array($parsed)) {
                Log::warning('GroqDiagnoser JSON parse error', ['content' => $content]);

                return $this->fallback($flags);
            }

            return [
                'diagnosis' => $parsed['diagnosis'] ?? 'No diagnosis available.',
                'recommended_action' => $parsed['recommended_action'] ?? 'Investigate manually.',
                'trigger_heal' => (bool) ($parsed['trigger_heal'] ?? false),
                'urgency' => in_array($parsed['urgency'] ?? '', ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'], true)
                    ? $parsed['urgency']
                    : 'MEDIUM',
            ];
        } catch (\Exception $e) {
            Log::error('GroqDiagnoser exception', ['error' => $e->getMessage()]);

            return $this->fallback($flags);
        }
    }

    /**
     * Generate a fallback diagnosis when Groq is unreachable.
     *
     * @param  array<int, string>  $flags
     * @return array{diagnosis: string, recommended_action: string, trigger_heal: bool, urgency: string}
     */
    protected function fallback(array $flags): array
    {
        if (empty($flags)) {
            return [
                'diagnosis' => 'No immediate issues detected by local heuristics.',
                'recommended_action' => 'Continue monitoring.',
                'trigger_heal' => false,
                'urgency' => 'LOW',
            ];
        }

        $diagnosis = 'Detected issues: '.implode(', ', $flags).'.';
        $recommendedAction = 'Review affected subsystems and restart services if needed.';
        $triggerHeal = in_array('high queue depth', $flags, true)
            || in_array('high failed jobs', $flags, true)
            || in_array('redis down', $flags, true);

        $urgency = in_array('redis down', $flags, true) || in_array('critical disk space', $flags, true)
            ? 'CRITICAL'
            : 'HIGH';

        return [
            'diagnosis' => $diagnosis,
            'recommended_action' => $recommendedAction,
            'trigger_heal' => $triggerHeal,
            'urgency' => $urgency,
        ];
    }
}
