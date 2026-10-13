<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Forms\Components\Section;
use Filament\Forms\Components\TagsInput;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Forms\Concerns\InteractsWithForms;
use Filament\Forms\Contracts\HasForms;
use Filament\Forms\Form;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class SystemAssistant extends Page implements HasForms
{
    use InteractsWithForms;

    protected static ?string $navigationIcon = 'heroicon-o-shield-check';

    protected static ?string $navigationGroup = 'System';

    protected static ?int $navigationSort = 3;

    protected static string $view = 'filament.pages.system-assistant';

    protected static ?string $title = 'System Assistant & Alerts';

    public ?array $data = [];

    public function mount(): void
    {
        $engine = app(SanaaEngineService::class);
        $prefs = $engine->getPreferences([
            'alert.enabled',
            'alert.recipients',
            'alert.threshold.cpu',
            'alert.threshold.ram',
            'alert.threshold.disk',
        ]);

        $alertsEnabledPref = $prefs['alert.enabled'] ?? true;
        $alertsEnabled = filter_var($alertsEnabledPref, FILTER_VALIDATE_BOOLEAN, FILTER_NULL_ON_FAILURE);
        if ($alertsEnabled === null) {
            $alertsEnabled = true;
        }

        $this->form->fill([
            'alerts_enabled' => $alertsEnabled,
            'alert_emails' => array_filter(explode(',', $prefs['alert.recipients'] ?? 'admin@sanaa.co')),
            'cpu_threshold' => $prefs['alert.threshold.cpu'] ?? 85,
            'ram_threshold' => $prefs['alert.threshold.ram'] ?? 80,
            'disk_threshold' => $prefs['alert.threshold.disk'] ?? 90,
        ]);
    }

    public function form(Form $form): Form
    {
        return $form
            ->schema([
                Section::make('Email Notifications')
                    ->description('Who should the Watchdog directly email when critical system issues arise?')
                    ->schema([
                        Toggle::make('alerts_enabled')
                            ->label('Enable Server Alerts')
                            ->default(true),
                        TagsInput::make('alert_emails')
                            ->label('Alert Recipients')
                            ->placeholder('New Email Address')
                            ->required(),
                    ]),
                Section::make('Alert Thresholds')
                    ->description('Set memory, disk, and CPU utilization limits before an alarm triggers.')
                    ->schema([
                        TextInput::make('cpu_threshold')
                            ->label('CPU Alert Threshold (%)')
                            ->numeric()
                            ->required()
                            ->minValue(1)
                            ->maxValue(100),
                        TextInput::make('ram_threshold')
                            ->label('RAM Alert Threshold (%)')
                            ->numeric()
                            ->required()
                            ->minValue(1)
                            ->maxValue(100),
                        TextInput::make('disk_threshold')
                            ->label('Disk Alert Threshold (%)')
                            ->numeric()
                            ->required()
                            ->minValue(1)
                            ->maxValue(100),
                    ])->columns(3),
            ])
            ->statePath('data');
    }

    public function submit(): void
    {
        $data = $this->form->getState();
        $engine = app(SanaaEngineService::class);

        $engine->updatePreference('alert.enabled', $data['alerts_enabled'] ? 'true' : 'false');

        // Convert tags to comma list for the python preference schema
        $emailList = implode(',', $data['alert_emails']);
        $engine->updatePreference('alert.recipients', $emailList);
        $engine->updatePreference('alert.threshold.cpu', $data['cpu_threshold']);
        $engine->updatePreference('alert.threshold.ram', $data['ram_threshold']);
        $engine->updatePreference('alert.threshold.disk', $data['disk_threshold']);

        Notification::make()
            ->title('Assistant Settings Saved')
            ->success()
            ->send();
    }
}
