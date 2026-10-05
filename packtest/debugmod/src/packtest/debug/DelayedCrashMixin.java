package packtest.debug;

import net.minecraft.CrashReport;
import net.minecraft.util.thread.BlockableEventLoop;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Test-only diagnostics: a worker's chunk generation exception is only "relayed" to the server thread, which never
 * reports it while it is itself blocked waiting for that chunk. Print it where it happens.
 */
@Mixin(BlockableEventLoop.class)
public class DelayedCrashMixin {
    @Inject(method = "relayDelayCrash", at = @At("HEAD"))
    private static void packtest$print(CrashReport report, CallbackInfo ci) {
        System.out.println("PACKTEST delayed crash: " + report.getTitle() + "\n" + report.getDetails());
        report.getException().printStackTrace(System.out);
    }
}
