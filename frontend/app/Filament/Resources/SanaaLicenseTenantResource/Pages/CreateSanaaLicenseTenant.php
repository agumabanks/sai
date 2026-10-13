<?php

namespace App\Filament\Resources\SanaaLicenseTenantResource\Pages;

use App\Filament\Resources\SanaaLicenseTenantResource;
use App\Models\SanaaLicenseTenant;
use Filament\Notifications\Notification;
use Filament\Resources\Pages\CreateRecord;

class CreateSanaaLicenseTenant extends CreateRecord
{
    protected static string $resource = SanaaLicenseTenantResource::class;

    protected ?string $generatedToken = null;

    protected function mutateFormDataBeforeCreate(array $data): array
    {
        return $data;
    }

    protected function handleRecordCreation(array $data): SanaaLicenseTenant
    {
        /** @var SanaaLicenseTenant $record */
        $record = static::getModel()::make($data);
        $this->generatedToken = $record->generateLicenseToken();
        $record->save();

        return $record;
    }

    protected function getCreatedNotification(): ?Notification
    {
        return Notification::make()
            ->title('Tenant created successfully')
            ->body('License token (copy now — shown once): '.($this->generatedToken ?? 'N/A'))
            ->success()
            ->persistent();
    }
}
