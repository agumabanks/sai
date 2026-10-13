<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class PendingApproval extends Model
{
    use HasFactory;

    protected $fillable = [
        'action',
        'target',
        'details',
        'requested_at',
        'approved_at',
        'approved_via',
        'token',
        'expires_at',
    ];

    protected $casts = [
        'details' => 'array',
        'requested_at' => 'datetime',
        'approved_at' => 'datetime',
        'expires_at' => 'datetime',
    ];
}
