<?php

namespace App\Filament\Pages;

use Filament\Pages\Page;
use App\Services\SanaaEngineService;
use Filament\Actions\Action;

class StrategicCommand extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-presentation-chart-line';
    protected static ?string $navigationGroup = 'Intelligence';
    protected static ?int $navigationSort = 2;
    protected static string $view = 'filament.pages.strategic-command';

    protected static ?string $title = 'Strategic Command Center';

    public array $signals = [];
    public bool $loading = true;

    public function mount(): void
    {
        $this->refreshSignals();
    }

    public function refreshSignals(): void
    {
        $engine = app(SanaaEngineService::class);
        $this->signals = $engine->getStrategicSignals(20);
        $this->loading = false;
    }

    public function getSignalColor(string $classification): string
    {
        return match(strtolower($classification)) {
            'opportunity' => 'emerald',
            'threat' => 'red',
            'policy' => 'blue',
            'market' => 'amber',
            default => 'gray',
        };
    }

    public function getSignalIcon(string $classification): string
    {
        return match(strtolower($classification)) {
            'opportunity' => 'heroicon-m-sparkles',
            'threat' => 'heroicon-m-exclamation-triangle',
            'policy' => 'heroicon-m-document-text',
            'market' => 'heroicon-m-chart-bar-square',
            default => 'heroicon-m-information-circle',
        };
    }

    protected function getHeaderActions(): array
    {
        return [
            Action::make('refresh')
                ->label('Refresh Signals')
                ->icon('heroicon-m-arrow-path')
                ->action(fn () => $this->refreshSignals()),
            Action::make('trigger_briefing')
                ->label('Run Intelligence Scan')
                ->icon('heroicon-m-magnifying-glass')
                ->color('info')
                ->requiresConfirmation()
                ->action(function() {
                    $engine = app(SanaaEngineService::class);
                    $engine->executeCommand("run daily briefing");
                    $this->refreshSignals();
                }),
        ];
    }
}
