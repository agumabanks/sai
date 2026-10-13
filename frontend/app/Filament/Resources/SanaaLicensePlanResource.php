<?php

namespace App\Filament\Resources;

use App\Filament\Resources\SanaaLicensePlanResource\Pages;
use App\Models\SanaaLicensePlan;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Table;

class SanaaLicensePlanResource extends Resource
{
    protected static ?string $model = SanaaLicensePlan::class;

    protected static ?string $navigationIcon = 'heroicon-o-document-currency-dollar';

    protected static ?string $navigationGroup = 'License Management';

    protected static ?string $modelLabel = 'Plan';

    protected static ?string $pluralModelLabel = 'Plans';

    public static function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\TextInput::make('name')
                    ->required()
                    ->maxLength(255),
                Forms\Components\TextInput::make('price_ugx')
                    ->required()
                    ->numeric()
                    ->integer()
                    ->prefix('UGX'),
                Forms\Components\TextInput::make('billing_cycle_days')
                    ->required()
                    ->numeric()
                    ->integer()
                    ->suffix('days'),
                Forms\Components\TextInput::make('max_members')
                    ->required()
                    ->numeric()
                    ->integer(),
                Forms\Components\TextInput::make('max_tellers')
                    ->required()
                    ->numeric()
                    ->integer(),
                Forms\Components\TextInput::make('max_loans_active')
                    ->required()
                    ->numeric()
                    ->integer(),
                Forms\Components\KeyValue::make('features')
                    ->keyLabel('Feature')
                    ->valueLabel('Value')
                    ->columnSpanFull(),
                Forms\Components\Toggle::make('is_active')
                    ->required()
                    ->default(true),
            ]);
    }

    public static function table(Table $table): Table
    {
        return $table
            ->columns([
                Tables\Columns\TextColumn::make('name')
                    ->searchable()
                    ->sortable(),
                Tables\Columns\TextColumn::make('price_ugx')
                    ->numeric()
                    ->prefix('UGX ')
                    ->sortable(),
                Tables\Columns\TextColumn::make('billing_cycle_days')
                    ->suffix(' days')
                    ->sortable(),
                Tables\Columns\IconColumn::make('is_active')
                    ->boolean()
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
                Tables\Filters\TernaryFilter::make('is_active')
                    ->label('Active'),
            ])
            ->actions([
                Tables\Actions\EditAction::make(),
                Tables\Actions\DeleteAction::make(),
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
            'index' => Pages\ListSanaaLicensePlans::route('/'),
            'create' => Pages\CreateSanaaLicensePlan::route('/create'),
            'edit' => Pages\EditSanaaLicensePlan::route('/{record}/edit'),
        ];
    }
}
