<?php

namespace App\Filament\Pages;

use Filament\Pages\Page;
use Symfony\Component\Process\Process;
use Symfony\Component\Process\Exception\ProcessFailedException;
use Illuminate\Support\Facades\Cache;

class SystemPlugins extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-puzzle-piece';
    protected static ?string $navigationGroup = 'System Operations';
    protected static ?int $navigationSort = 3;
    protected static string $view = 'filament.pages.system-plugins';
    protected static ?string $title = 'System Plugins & Packages';

    public bool $isScanning = false;
    public string $composerOutput = '';
    public string $npmOutput = '';

    public function mount()
    {
        $this->composerOutput = Cache::get('system_plugins_composer', 'No recent scan data. Click "Scan for Updates" to check.');
        $this->npmOutput = Cache::get('system_plugins_npm', 'No recent scan data.');
    }

    public function scanNow()
    {
        $this->isScanning = true;
        
        try {
            // Composer OUTDATED
            $process = new Process(['composer', 'show', '--latest', '-D', '-m'], base_path());
            $process->setTimeout(60);
            $process->run();
            $this->composerOutput = $process->getOutput();
            if (empty($this->composerOutput)) {
                $this->composerOutput = "All composer packages are up to date.";
            }
            Cache::put('system_plugins_composer', $this->composerOutput, now()->addHours(12));

            // NPM OUTDATED
            $processNpm = new Process(['npm', 'outdated'], base_path());
            $processNpm->setTimeout(60);
            $processNpm->run();
            // npm outdated returns exit code 1 if there are outdated packages
            $this->npmOutput = $processNpm->getOutput();
            if (empty($this->npmOutput)) {
                $this->npmOutput = "All npm packages are up to date.";
            }
            Cache::put('system_plugins_npm', $this->npmOutput, now()->addHours(12));

        } catch (\Exception $e) {
            $this->composerOutput = "Error running scan: " . $e->getMessage();
        }

        $this->isScanning = false;
    }
}
