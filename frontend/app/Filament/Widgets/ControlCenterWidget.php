<?php

namespace App\Filament\Widgets;

use App\Services\SanaaEngineService;
use Filament\Widgets\Widget;

class ControlCenterWidget extends Widget
{
    protected static string $view = 'filament.widgets.control-center-widget';

    protected static bool $isLazy = false;

    public string $currentProvider = 'local';

    public function mount()
    {
        $engine = app(SanaaEngineService::class);
        $status = $engine->getStatus();
        // Fix: API returns channels.active_provider not channels.web.active_provider
        $this->currentProvider = $status['channels']['active_provider'] ?? 'local';
    }

    public function switchProvider(string $provider)
    {
        $engine = app(SanaaEngineService::class);
        
        if ($engine->setProvider($provider)) {
            $this->currentProvider = $provider;
            
            \Filament\Notifications\Notification::make()
                ->title("Brain Switched")
                ->body("Intelligence provider switched to " . strtoupper($provider))
                ->success()
                ->send();
                
            // Refresh the page to update all metrics
            $this->dispatch('$refresh');
        } else {
            \Filament\Notifications\Notification::make()
                ->title("Switch Failed")
                ->body("Could not switch to " . strtoupper($provider) . ". Check logs for details.")
                ->danger()
                ->send();
        }
    }

    public function triggerScan()
    {
        $engine = app(SanaaEngineService::class);
        $engine->executeCommand('scan');

        \Filament\Notifications\Notification::make()
            ->title("Scan Initiated")
            ->body("Autonomous security audit running in background.")
            ->info()
            ->send();
    }

    public function triggerBriefing()
    {
        $engine = app(SanaaEngineService::class);
        $engine->executeCommand('generate briefing');

        \Filament\Notifications\Notification::make()
            ->title("Briefing Started")
            ->body("Intelligence briefing is being generated. Newsletter will be sent to your email.")
            ->info()
            ->send();
    }
}
