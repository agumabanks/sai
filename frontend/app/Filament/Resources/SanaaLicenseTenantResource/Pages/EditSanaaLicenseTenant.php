<?php

namespace App\Filament\Resources\SanaaLicenseTenantResource\Pages;

use App\Filament\Resources\SanaaLicenseTenantResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditSanaaLicenseTenant extends EditRecord
{
    protected static string $resource = SanaaLicenseTenantResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\DeleteAction::make(),
        ];
    }
}
