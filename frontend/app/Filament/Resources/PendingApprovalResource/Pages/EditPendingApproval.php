<?php

namespace App\Filament\Resources\PendingApprovalResource\Pages;

use App\Filament\Resources\PendingApprovalResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditPendingApproval extends EditRecord
{
    protected static string $resource = PendingApprovalResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\ViewAction::make(),
            Actions\DeleteAction::make(),
        ];
    }
}
