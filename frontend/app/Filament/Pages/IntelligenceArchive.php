<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Pages\Page;

class IntelligenceArchive extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-archive-box';

    protected static string $view = 'filament.pages.intelligence-archive';

    protected static ?string $navigationGroup = 'Intelligence';

    public array $briefings = [];
    public ?array $selectedBriefing = null;
    public ?array $latestSignal = null;

    public function mount()
    {
        $this->refreshData();
    }

    public function refreshData()
    {
        $engine = app(SanaaEngineService::class);
        $this->briefings = $engine->getBriefings();
        $this->latestSignal = $engine->getLatestSignal();
    }

    public function selectBriefing(int $id)
    {
        $engine = app(SanaaEngineService::class);
        $this->selectedBriefing = $engine->getBriefing($id);
    }

    public function closeBriefing()
    {
        $this->selectedBriefing = null;
    }
}
