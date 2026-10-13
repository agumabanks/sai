<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class SokoCommand extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-shopping-bag';

    protected static ?string $navigationGroup = 'Infrastructure';

    protected static ?int $navigationSort = 12;

    protected static string $view = 'filament.pages.soko-command';

    protected static ?string $title = 'Soko';

    protected static ?string $navigationLabel = 'Soko';

    public array $metrics = [];

    public array $distressed = [];

    public array $health = [];

    public string $detailOutput = '';

    public string $activeTab = 'overview';

    public bool $isLoading = false;

    public function mount(): void
    {
        $this->redirect(url('/?launch=sokocommand'));
    }

    public function loadOverview(): void
    {
        $this->isLoading = true;
        $engine = app(SanaaEngineService::class);

        // Fetch platform health
        $healthRes = $engine->runSkill('soko_agent', ['action' => 'platform_health'], 'admin:soko_command');
        $this->health = $healthRes['data'] ?? [];

        // Fetch order metrics
        $metricsRes = $engine->runSkill('soko_agent', ['action' => 'order_metrics'], 'admin:soko_command');
        $this->metrics = $metricsRes['data'] ?? [];

        $this->isLoading = false;
    }

    public function runCheck(string $action): void
    {
        $this->isLoading = true;
        $this->activeTab = $action;

        $engine = app(SanaaEngineService::class);
        $result = $engine->runSkill('soko_agent', ['action' => $action, 'limit' => 50], 'admin:soko_command');

        $this->detailOutput = (string) ($result['output'] ?? ($result['error'] ?? 'No data'));

        if ($action === 'distressed_sellers') {
            $this->distressed = $result['data']['sellers'] ?? [];
        }

        $this->isLoading = false;

        $success = $result['success'] ?? false;
        if ($success) {
            Notification::make()->title(ucfirst(str_replace('_', ' ', $action)).' check complete')->success()->send();
        } else {
            Notification::make()->title(ucfirst(str_replace('_', ' ', $action)).' check failed')->danger()->send();
        }
    }

    public function refreshAll(): void
    {
        $this->detailOutput = '';
        $this->activeTab = 'overview';
        $this->loadOverview();
        Notification::make()->title('Soko Dashboard refreshed')->success()->send();
    }
}
