<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('sanaa_license_payments', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('tenant_id')->constrained('sanaa_license_tenants');
            $table->integer('amount_ugx');
            $table->enum('payment_method', ['cash', 'mobile_money', 'bank_transfer', 'pesapal']);
            $table->string('reference')->nullable();
            $table->timestamp('paid_at');
            $table->integer('extends_subscription_by_days');
            $table->timestamp('new_subscription_ends_at');
            $table->string('recorded_by');
            $table->text('notes')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('sanaa_license_payments');
    }
};
