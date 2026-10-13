<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class SanaaHealthLog extends Model
{
    use HasFactory, HasUuids;

    protected $table = 'sanaa_health_log';

    protected $keyType = 'string';

    public $incrementing = false;

    protected $guarded = [];

    protected $casts = [
        'signals' => 'array',
        'heal_response' => 'array',
        'created_at' => 'datetime',
        'updated_at' => 'datetime',
    ];
}
