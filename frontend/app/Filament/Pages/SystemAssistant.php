<?php

namespace App\Filament\Pages;

use Filament\Pages\Page;
use Filament\Forms\Contracts\HasForms;
use Filament\Forms\Concerns\InteractsWithForms;
use Filament\Forms\Form;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Section;
use Filament\Forms\Components\TagsInput;
use Filament\Notifications\Notification;
use App\Services\SanaaEngineService;

class SystemAssistant extends Page implements HasForms
{
    use InteractsWithForms;

    protected static ?string $navigationIcon = 'heroicon-o-shield-check';
    protected static ?string $navigationGroup = 'System Operations';
    protected static ?int $navigationSort = 4;
    protected static string $view = 'filament.pages.system-assistant';
    protected static ?string $title = 'System Assistant & Alerts';

    public ?array $data = [];

    public function mount(): void
    {
        $this->form->fill([
            'alert_emails' => ['admin@sanaa.co'],
            'cpu_threshold' => 85,
            'ram_threshold' => 80,
            'disk_threshold' => 90,
        ]);
    }

    public function form(Form $form): Form
    {
        return $form
            ->schema([
                Section::make('Email Notifications')
                    ->description('Who should the Watchdog directly email when critical system issues arise?')
                    ->schema([
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
