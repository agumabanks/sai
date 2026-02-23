<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Pages\Page;

class SystemDoctor extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-heart';
    protected static ?string $navigationGroup = 'Operations';
    protected static ?int $navigationSort = 4;
    protected static string $view = 'filament.pages.system-doctor';

    public array $report = [];
    public array $watchdogAdvisor = [];
    public array $briefingQa = [];

    public function mount(): void
    {
        $this->refreshData();
    }

    public function refreshData(): void
    {
        $engine = app(SanaaEngineService::class);
        $this->report = $engine->getDoctorReport();
        $this->watchdogAdvisor = $engine->getWatchdogAdvisor();
        $this->briefingQa = $engine->getLatestBriefingQa();
    }
}

