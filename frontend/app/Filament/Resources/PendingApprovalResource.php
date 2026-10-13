<?php

namespace App\Filament\Resources;

use App\Filament\Resources\PendingApprovalResource\Pages;
use App\Models\PendingApproval;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Table;

class PendingApprovalResource extends Resource
{
    protected static ?string $model = PendingApproval::class;

    protected static ?string $navigationIcon = 'heroicon-o-shield-check';

    protected static ?string $navigationGroup = 'System';

    public static function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\TextInput::make('action')
                    ->required()
                    ->maxLength(255),
                Forms\Components\TextInput::make('target')
                    ->required()
                    ->maxLength(255),
                Forms\Components\KeyValue::make('details')
                    ->columnSpanFull(),
                Forms\Components\DateTimePicker::make('requested_at')
                    ->required(),
                Forms\Components\DateTimePicker::make('approved_at'),
                Forms\Components\Select::make('approved_via')
                    ->options([
                        'whatsapp' => 'WhatsApp',
                        'email' => 'Email',
                        'dashboard' => 'Dashboard',
                    ]),
                Forms\Components\TextInput::make('token')
                    ->required()
                    ->maxLength(255),
                Forms\Components\DateTimePicker::make('expires_at')
                    ->required(),
            ]);
    }

    public static function table(Table $table): Table
    {
        return $table
            ->columns([
                Tables\Columns\TextColumn::make('action')
                    ->searchable(),
                Tables\Columns\TextColumn::make('target')
                    ->searchable(),
                Tables\Columns\TextColumn::make('requested_at')
                    ->dateTime()
                    ->sortable(),
                Tables\Columns\TextColumn::make('approved_at')
                    ->dateTime()
                    ->sortable(),
                Tables\Columns\TextColumn::make('approved_via')
                    ->searchable(),
                Tables\Columns\TextColumn::make('expires_at')
                    ->dateTime()
                    ->sortable(),
                Tables\Columns\TextColumn::make('created_at')
                    ->dateTime()
                    ->sortable()
                    ->toggleable(isToggledHiddenByDefault: true),
                Tables\Columns\TextColumn::make('updated_at')
                    ->dateTime()
                    ->sortable()
                    ->toggleable(isToggledHiddenByDefault: true),
            ])
            ->filters([
                //
            ])
            ->actions([
                Tables\Actions\ViewAction::make(),
                Tables\Actions\EditAction::make(),
                Tables\Actions\Action::make('approve')
                    ->label('Approve')
                    ->icon('heroicon-o-check-circle')
                    ->color('success')
                    ->requiresConfirmation()
                    ->hidden(fn (PendingApproval $record): bool => $record->approved_at !== null)
                    ->action(function (PendingApproval $record) {
                        $record->update([
                            'approved_at' => now(),
                            'approved_via' => 'dashboard',
                        ]);
                    }),
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
            'index' => Pages\ListPendingApprovals::route('/'),
            'create' => Pages\CreatePendingApproval::route('/create'),
            'view' => Pages\ViewPendingApproval::route('/{record}'),
            'edit' => Pages\EditPendingApproval::route('/{record}/edit'),
        ];
    }
}
