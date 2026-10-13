<?php

namespace App\Filament\Resources\PendingApprovalResource\Pages;

use App\Filament\Resources\PendingApprovalResource;
use Filament\Actions;
use Filament\Resources\Pages\ListRecords;

class ListPendingApprovals extends ListRecords
{
    protected static string $resource = PendingApprovalResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\CreateAction::make(),
        ];
    }
}
