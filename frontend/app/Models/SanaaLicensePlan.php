<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class SanaaLicensePlan extends Model
{
    use HasFactory, HasUuids;

    protected $keyType = 'string';

    public $incrementing = false;

    protected $guarded = [];

    protected $casts = [
        'features' => 'array',
        'is_active' => 'boolean',
        'price_ugx' => 'integer',
        'billing_cycle_days' => 'integer',
        'max_members' => 'integer',
        'max_tellers' => 'integer',
        'max_loans_active' => 'integer',
        'created_at' => 'datetime',
        'updated_at' => 'datetime',
    ];

    public function tenants(): HasMany
    {
        return $this->hasMany(SanaaLicenseTenant::class, 'plan_id');
    }
}
