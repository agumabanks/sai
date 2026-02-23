<?php

namespace App\Filament\Widgets;

use App\Services\SanaaEngineService;
use Filament\Widgets\Widget;

class IntelligencePreviewWidget extends Widget
{
    protected static string $view = 'filament.widgets.intelligence-preview-widget';

    protected static ?string $pollingInterval = '30s';

    protected static bool $isLazy = false;

    public ?array $latestBriefing = null;
    public ?array $latestSignal = null;
    public int $briefingCount = 0;

    public function mount()
    {
        $this->refreshIntelligence();
    }

    public function refreshIntelligence()
    {
        $engine = app(SanaaEngineService::class);

        // Latest briefing
        $briefings = $engine->getBriefings(5);
        $this->briefingCount = count($briefings);

        if (!empty($briefings)) {
            $first = $briefings[0];
            $this->latestBriefing = [
                'id' => $first['id'] ?? 0,
                'title' => $first['title'] ?? 'Untitled',
                'time' => isset($first['created_at']) ? \Carbon\Carbon::parse($first['created_at']) : now(),
                'articleCount' => $first['metadata']['article_count'] ?? 0,
                'topics' => $first['metadata']['topics'] ?? [],
            ];
        }

        // Latest strategic signal
        $signal = $engine->getLatestSignal();
        if (isset($signal['title'])) {
            $this->latestSignal = [
                'title' => $signal['title'],
                'score' => $signal['score'] ?? 0,
                'time' => isset($signal['created_at']) ? \Carbon\Carbon::parse($signal['created_at']) : now(),
            ];
        }
    }
}
