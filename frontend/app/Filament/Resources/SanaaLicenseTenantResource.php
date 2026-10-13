<?php

namespace App\Filament\Resources;

use App\Filament\Resources\SanaaLicenseTenantResource\Pages;
use App\Models\SanaaLicenseEvent;
use App\Models\SanaaLicensePayment;
use App\Models\SanaaLicensePlan;
use App\Models\SanaaLicenseTenant;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Notifications\Notification;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;

class SanaaLicenseTenantResource extends Resource
{
    protected static ?string $model = SanaaLicenseTenant::class;

    protected static ?string $navigationIcon = 'heroicon-o-key';

    protected static ?string $navigationGroup = 'License Management';

    protected static ?string $modelLabel = 'Tenant';

    protected static ?string $pluralModelLabel = 'Tenants';

    public static function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\Section::make('Tenant Information')
                    ->schema([
                        Forms\Components\TextInput::make('tenant_key')
                            ->required()
                            ->unique(ignoreRecord: true)
                            ->maxLength(255),
                        Forms\Components\TextInput::make('tenant_name')
                            ->required()
                            ->maxLength(255),
                        Forms\Components\TextInput::make('contact_name')
                            ->maxLength(255),
                        Forms\Components\TextInput::make('contact_phone')
                            ->tel()
                            ->maxLength(255),
                        Forms\Components\TextInput::make('contact_email')
                            ->email()
                            ->maxLength(255),
                    ])
                    ->columns(2),

                Forms\Components\Section::make('License Status')
                    ->schema([
                        Forms\Components\Select::make('plan_id')
                            ->label('Plan')
                            ->options(fn () => SanaaLicensePlan::query()->pluck('name', 'id'))
                            ->searchable()
                            ->required(),
                        Forms\Components\Select::make('status')
                            ->options([
                                'trial' => 'Trial',
                                'active' => 'Active',
                                'grace' => 'Grace',
                                'suspended' => 'Suspended',
                                'terminated' => 'Terminated',
                            ])
                            ->required(),
                        Forms\Components\DateTimePicker::make('trial_ends_at'),
                        Forms\Components\DateTimePicker::make('subscription_starts_at'),
                        Forms\Components\DateTimePicker::make('subscription_ends_at'),
                        Forms\Components\TextInput::make('grace_period_days')
                            ->numeric()
                            ->integer()
                            ->default(7),
                        Forms\Components\Toggle::make('kill_switch_active')
                            ->label('Kill Switch Active')
                            ->default(false),
                    ])
                    ->columns(2),

                Forms\Components\Section::make('Token & Notes')
                    ->schema([
                        Forms\Components\Textarea::make('notes')
                            ->columnSpanFull()
                            ->rows(3),
                        Forms\Components\Placeholder::make('license_token_hint')
                            ->label('License Token')
                            ->content('Auto-generated on creation.'),
                    ]),
            ]);
    }

    public static function table(Table $table): Table
    {
        return $table
            ->columns([
                Tables\Columns\TextColumn::make('tenant_name')
                    ->searchable()
                    ->sortable(),
                Tables\Columns\TextColumn::make('plan.name')
                    ->badge()
                    ->color('primary')
                    ->sortable(),
                Tables\Columns\TextColumn::make('status')
                    ->badge()
                    ->color(fn (SanaaLicenseTenant $record): string => $record->statusBadgeColor())
                    ->sortable(),
                Tables\Columns\TextColumn::make('subscription_ends_at')
                    ->label('Expires At')
                    ->dateTime()
                    ->sortable(),
                Tables\Columns\TextColumn::make('days_left')
                    ->label('Days Left')
                    ->state(fn (SanaaLicenseTenant $record): int => $record->daysUntilExpiry())
                    ->numeric()
                    ->sortable(query: fn ($query, $direction) => $query->orderBy('subscription_ends_at', $direction))
                    ->color(fn (int $state): string => match (true) {
                        $state < 0 => 'danger',
                        $state <= 7 => 'warning',
                        default => 'success',
                    }),
                Tables\Columns\IconColumn::make('kill_switch_active')
                    ->label('Kill Switch')
                    ->boolean()
                    ->sortable(),
                Tables\Columns\TextColumn::make('last_checked_at')
                    ->dateTime()
                    ->sortable()
                    ->toggleable(isToggledHiddenByDefault: true),
            ])
            ->filters([
                Tables\Filters\SelectFilter::make('status')
                    ->options([
                        'trial' => 'Trial',
                        'active' => 'Active',
                        'grace' => 'Grace',
                        'suspended' => 'Suspended',
                        'terminated' => 'Terminated',
                    ]),
                Tables\Filters\SelectFilter::make('plan_id')
                    ->label('Plan')
                    ->options(fn () => SanaaLicensePlan::query()->pluck('name', 'id'))
                    ->searchable(),
                Tables\Filters\Filter::make('expiring_7_days')
                    ->label('Expiring within 7 days')
                    ->query(fn ($query) => $query->where('subscription_ends_at', '<=', now()->addDays(7))),
                Tables\Filters\Filter::make('expiring_30_days')
                    ->label('Expiring within 30 days')
                    ->query(fn ($query) => $query->where('subscription_ends_at', '<=', now()->addDays(30))),
            ])
            ->actions([
                Tables\Actions\Action::make('recordPayment')
                    ->label('Record Payment')
                    ->icon('heroicon-o-banknotes')
                    ->color('success')
                    ->form([
                        Forms\Components\TextInput::make('amount_ugx')
                            ->required()
                            ->numeric()
                            ->integer()
                            ->prefix('UGX'),
                        Forms\Components\Select::make('payment_method')
                            ->required()
                            ->options([
                                'cash' => 'Cash',
                                'mobile_money' => 'Mobile Money',
                                'bank_transfer' => 'Bank Transfer',
                                'pesapal' => 'Pesapal',
                            ]),
                        Forms\Components\TextInput::make('reference')
                            ->maxLength(255),
                        Forms\Components\DateTimePicker::make('paid_at')
                            ->required()
                            ->default(now()),
                        Forms\Components\TextInput::make('extends_by_days')
                            ->required()
                            ->numeric()
                            ->integer()
                            ->suffix('days'),
                        Forms\Components\Textarea::make('notes')
                            ->rows(2),
                    ])
                    ->action(function (SanaaLicenseTenant $record, array $data): void {
                        $newEndsAt = $record->subscription_ends_at
                            ? $record->subscription_ends_at->copy()->addDays((int) $data['extends_by_days'])
                            : now()->addDays((int) $data['extends_by_days']);

                        $payment = SanaaLicensePayment::create([
                            'tenant_id' => $record->id,
                            'amount_ugx' => $data['amount_ugx'],
                            'payment_method' => $data['payment_method'],
                            'reference' => $data['reference'] ?? null,
                            'paid_at' => $data['paid_at'],
                            'extends_subscription_by_days' => $data['extends_by_days'],
                            'new_subscription_ends_at' => $newEndsAt,
                            'recorded_by' => Auth::user()?->name ?? 'Admin',
                            'notes' => $data['notes'] ?? null,
                        ]);

                        $record->update([
                            'subscription_ends_at' => $newEndsAt,
                            'status' => 'active',
                        ]);

                        SanaaLicenseEvent::create([
                            'tenant_id' => $record->id,
                            'event_type' => 'payment_recorded',
                            'triggered_by' => 'admin',
                            'payload' => [
                                'payment_id' => $payment->id,
                                'amount_ugx' => $payment->amount_ugx,
                                'extends_by_days' => $payment->extends_subscription_by_days,
                            ],
                            'created_at' => now(),
                        ]);

                        try {
                            app(\App\Services\SanaaDoctor\WhatsAppNotifier::class)->sendPaymentConfirmation($record, $payment);
                        } catch (\Throwable $e) {
                            // Method may not exist; fail silently.
                        }

                        Notification::make()
                            ->title('Payment recorded successfully')
                            ->success()
                            ->send();
                    })
                    ->modalSubmitActionLabel('Record Payment'),

                Tables\Actions\Action::make('toggleKillSwitch')
                    ->label('Toggle Kill Switch')
                    ->icon('heroicon-o-no-symbol')
                    ->color('danger')
                    ->requiresConfirmation()
                    ->action(function (SanaaLicenseTenant $record): void {
                        $record->update(['kill_switch_active' => ! $record->kill_switch_active]);

                        Notification::make()
                            ->title('Kill switch toggled')
                            ->body('New state: '.($record->kill_switch_active ? 'Active' : 'Inactive'))
                            ->success()
                            ->send();
                    }),

                Tables\Actions\Action::make('changePlan')
                    ->label('Change Plan')
                    ->icon('heroicon-o-arrow-path')
                    ->color('warning')
                    ->form([
                        Forms\Components\Select::make('plan_id')
                            ->label('New Plan')
                            ->options(fn () => SanaaLicensePlan::query()->pluck('name', 'id'))
                            ->searchable()
                            ->required(),
                    ])
                    ->action(function (SanaaLicenseTenant $record, array $data): void {
                        $oldPlanId = $record->plan_id;
                        $record->update(['plan_id' => $data['plan_id']]);

                        SanaaLicenseEvent::create([
                            'tenant_id' => $record->id,
                            'event_type' => 'plan_changed',
                            'triggered_by' => 'admin',
                            'payload' => [
                                'old_plan_id' => $oldPlanId,
                                'new_plan_id' => $data['plan_id'],
                            ],
                            'created_at' => now(),
                        ]);

                        Notification::make()
                            ->title('Plan changed successfully')
                            ->success()
                            ->send();
                    })
                    ->modalSubmitActionLabel('Change Plan'),

                Tables\Actions\Action::make('viewEvents')
                    ->label('View Events')
                    ->icon('heroicon-o-clock')
                    ->slideOver()
                    ->modalContent(function (SanaaLicenseTenant $record) {
                        $events = SanaaLicenseEvent::query()
                            ->where('tenant_id', $record->id)
                            ->latest('created_at')
                            ->limit(50)
                            ->get();

                        return view('filament.widgets.sanaa-license-tenant-events', [
                            'events' => $events,
                        ]);
                    })
                    ->modalSubmitAction(false)
                    ->modalCancelActionLabel('Close'),

                Tables\Actions\EditAction::make(),
            ])
            ->bulkActions([
                Tables\Actions\BulkActionGroup::make([
                    Tables\Actions\DeleteBulkAction::make(),
                ]),
            ]);
    }

    public static function getRelations(): array
    {
        return [
            //
        ];
    }

    public static function getPages(): array
    {
        return [
            'index' => Pages\ListSanaaLicenseTenants::route('/'),
            'create' => Pages\CreateSanaaLicenseTenant::route('/create'),
            'edit' => Pages\EditSanaaLicenseTenant::route('/{record}/edit'),
        ];
    }
}
