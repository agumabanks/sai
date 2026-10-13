<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('sanaa_license_tenants', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->string('tenant_key')->unique();
            $table->string('tenant_name');
            $table->string('contact_name');
            $table->string('contact_phone');
            $table->string('contact_email')->nullable();
            $table->foreignUuid('plan_id')->constrained('sanaa_license_plans');
            $table->enum('status', ['trial', 'active', 'grace', 'suspended', 'terminated']);
            $table->timestamp('trial_ends_at')->nullable();
            $table->timestamp('subscription_starts_at');
            $table->timestamp('subscription_ends_at');
            $table->integer('grace_period_days')->default(7);
            $table->string('license_token');
            $table->boolean('kill_switch_active')->default(false);
            $table->text('notes')->nullable();
            $table->timestamp('last_checked_at')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('sanaa_license_tenants');
    }
};
