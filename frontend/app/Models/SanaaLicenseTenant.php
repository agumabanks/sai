<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Support\Facades\Hash;

class SanaaLicenseTenant extends Model
{
    use HasFactory, HasUuids;

    protected $table = 'sanaa_license_tenants';

    protected $keyType = 'string';

    public $incrementing = false;

    protected $guarded = [];

    protected $casts = [
        'trial_ends_at' => 'datetime',
        'subscription_starts_at' => 'datetime',
        'subscription_ends_at' => 'datetime',
        'last_checked_at' => 'datetime',
        'kill_switch_active' => 'boolean',
        'grace_period_days' => 'integer',
    ];

    public function plan(): BelongsTo
    {
        return $this->belongsTo(SanaaLicensePlan::class, 'plan_id');
    }

    public function payments(): HasMany
    {
        return $this->hasMany(SanaaLicensePayment::class, 'tenant_id');
    }

    public function events(): HasMany
    {
        return $this->hasMany(SanaaLicenseEvent::class, 'tenant_id');
    }

    public function isExpired(): bool
    {
        if ($this->subscription_ends_at === null) {
            return false;
        }

        $graceEnds = $this->subscription_ends_at->copy()->addDays($this->grace_period_days);

        return now()->greaterThan($graceEnds);
    }

    public function isInGrace(): bool
    {
        if ($this->subscription_ends_at === null) {
            return false;
        }

        $graceEnds = $this->subscription_ends_at->copy()->addDays($this->grace_period_days);

        return now()->greaterThan($this->subscription_ends_at) && now()->lessThanOrEqualTo($graceEnds);
    }

    public function daysUntilExpiry(): int
    {
        if ($this->subscription_ends_at === null) {
            return 0;
        }

        return (int) now()->startOfDay()->diffInDays($this->subscription_ends_at->copy()->startOfDay(), false);
    }

    public function isAccessAllowed(): bool
    {
        if ($this->kill_switch_active) {
            return false;
        }

        if (in_array($this->status, ['active', 'trial'], true)) {
            return true;
        }

        if ($this->status === 'grace') {
            return ! $this->isExpired();
        }

        return false;
    }

    public function statusBadgeColor(): string
    {
        return match ($this->status) {
            'active' => 'success',
            'trial' => 'info',
            'grace' => 'warning',
            'suspended', 'terminated' => 'danger',
            default => 'gray',
        };
    }

    public function setLicenseToken(string $plainToken): void
    {
        $this->license_token = Hash::make($plainToken);
    }

    public function verifyLicenseToken(string $plainToken): bool
    {
        return Hash::check($plainToken, $this->license_token);
    }

    public function generateLicenseToken(): string
    {
        $token = \Illuminate\Support\Str::random(64);
        $this->setLicenseToken($token);

        return $token;
    }
}
