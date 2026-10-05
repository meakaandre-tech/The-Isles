package packtest.debug;

import net.minecraft.server.level.ChunkMap;
import net.minecraft.server.level.GenerationChunkHolder;
import net.minecraft.util.StaticCache2D;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.chunk.status.ChunkStep;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Test-only diagnostics: says which chunk and status a generation step is about when its parent status is missing. */
@Mixin(ChunkMap.class)
public class ChunkMapMixin {
    @Inject(method = "applyStep", at = @At("HEAD"))
    private void packtest$parentMissing(GenerationChunkHolder holder, ChunkStep step, StaticCache2D<GenerationChunkHolder> cache, CallbackInfoReturnable<?> cir) {
        ChunkStatus target = step.targetStatus();
        if (target == ChunkStatus.EMPTY) return;
        GenerationChunkHolder h = cache.get(holder.getPos().x(), holder.getPos().z());
        if (h.getChunkIfPresentUnchecked(target.getParent()) != null) return;
        StringBuilder sb = new StringBuilder("PACKTEST parent missing: chunk " + holder.getPos() + " target " + target + " parent " + target.getParent()
                + " sameHolder=" + (h == holder) + " persisted=" + holder.getPersistedStatus() + " latest=" + holder.getLatestStatus()
                + " ticketLevel=" + holder.getTicketLevel() + " full=" + holder.getFullStatus() + " step=" + step + "\n  futures:");
        for (var p : h.getAllFutures()) {
            var f = p.getSecond();
            sb.append(' ').append(p.getFirst()).append('=').append(f == null ? "null" : !f.isDone() ? "pending" : f.isCompletedExceptionally() ? "exception" : String.valueOf(f.getNow(null)));
        }
        System.out.println(sb);
        new Throwable("PACKTEST stack").printStackTrace(System.out);
    }
}
