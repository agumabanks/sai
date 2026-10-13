<?php

namespace App\Filament\Widgets;

use App\Services\SanaaEngineService;
use App\Support\SanaaSettings;
use App\Support\SanaaShell;
use Filament\Widgets\Widget;

class ControlCenterWidget extends Widget
{
    protected static string $view = 'filament.widgets.control-center-widget';

    protected static bool $isLazy = false;

    public string $currentProvider = 'groq';

    public array $metrics = [];

    public array $controlCenter = [];

    public array $quickLaunch = [];

    public function mount(): void
    {
        $this->refreshState();
    }

    public function refreshState(): void
    {
        $engine = app(SanaaEngineService::class);
        $status = $engine->getStatus();
        $live = SanaaShell::liveData(SanaaShell::metricsFromStatus($status));

        $this->currentProvider = $status['channels']['active_provider'] ?? 'groq';
        $this->metrics = $live['metrics'] ?? [];
        $this->controlCenter = SanaaSettings::controlCenter();
        $this->quickLaunch = collect(SanaaShell::quickLaunch())->take(4)->values()->all();
    }

    public function switchProvider(string $provider): void
    {
        if ($provider !== 'groq') {
            \Filament\Notifications\Notification::make()
                ->title('Groq Only')
                ->body('Sanaa AI is locked to Groq for now.')
                ->warning()
                ->send();

            return;
        }

        $engine = app(SanaaEngineService::class);

        if ($engine->setProvider($provider)) {
            $this->currentProvider = $provider;
            $this->refreshState();

            \Filament\Notifications\Notification::make()
                ->title('Brain Switched')
                ->body('Intelligence provider switched to '.strtoupper($provider))
                ->success()
                ->send();
        } else {
            \Filament\Notifications\Notification::make()
                ->title('Switch Failed')
                ->body('Could not switch to '.strtoupper($provider).'. Check logs for details.')
                ->danger()
                ->send();
        }
    }

    public function triggerScan(): void
    {
        app(SanaaEngineService::class)->executeCommand('scan');

        \Filament\Notifications\Notification::make()
            ->title('Scan Initiated')
            ->body('Autonomous security audit running in background.')
            ->info()
            ->send();
    }

    public function triggerBriefing(): void
    {
        app(SanaaEngineService::class)->executeCommand('generate briefing');

        \Filament\Notifications\Notification::make()
            ->title('Briefing Started')
            ->body('Intelligence briefing is being generated. Newsletter will be sent to your email.')
            ->info()
            ->send();
    }

    public function openModule(string $moduleId): void
    {
        $module = collect($this->controlCenter['modules'] ?? [])->firstWhere('id', $moduleId);

        if (! empty($module['url'])) {
            $this->redirect($module['url']);
        }
    }
}
