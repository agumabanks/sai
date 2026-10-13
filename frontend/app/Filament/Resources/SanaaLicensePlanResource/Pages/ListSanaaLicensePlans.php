<?php

namespace App\Filament\Resources\SanaaLicensePlanResource\Pages;

use App\Filament\Resources\SanaaLicensePlanResource;
use Filament\Actions;
use Filament\Resources\Pages\ListRecords;

class ListSanaaLicensePlans extends ListRecords
{
    protected static string $resource = SanaaLicensePlanResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\CreateAction::make(),
        ];
    }
}
