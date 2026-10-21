/*
 * HASTE Version-IV -- bare-metal on-board measurement application (Zynq-7000 PS).
 *
 * Talks to the PL wrapper board/rtl/snn_board.sv (register map in
 * board/README.md) and prints over the PS UART (115200 8N1):
 *
 *   phase 1  LATENCY : every image of spikes.bin once, printing
 *                        SPK k t class                       (output spikes, in order)
 *                        IMG k LABEL l HID h OVF o CYCLES c COUNTS c0 .. c9
 *                        TIME k XTIME_NS n HW_NS m
 *                      IMG/SPK lines are byte-compatible with tb/tb_snn.sv
 *                      (compare with board/tools/compare_results.py).
 *   phase 2+ POWER   : rounds of  IDLE (core held in reset, same PS/AXI traffic, IDLE_MS)
 *                               + CONT (continuous inference over all images, CONT_MS),
 *                      forever (or POWER_ROUNDS rounds), with progress lines.
 *
 * Inputs in DDR (loaded by board/sw/run_board.tcl with "dow -data"):
 *   SPIKES_ADDR : spikes.bin  (header u32 magic 0x534E4E53, n_img, rows, n_in; then rows)
 *   LABELS_ADDR : labels.bin  (header u32 magic 0x4C4E4E53, n_img; then u8 labels)
 * made by board/tools/make_bin.py.
 *
 * Everything board-specific is a #define below with its default.
 */
#include <stdio.h>
#include "xil_types.h"
#include "xil_io.h"
#include "xil_cache.h"
#include "xtime_l.h"

/* ------------------------------------------------------------ configuration */
#ifndef SNN_BASE
#define SNN_BASE 0x43C00000u /* = build_board.tcl BASE_ADDR */
#endif
#ifndef SPIKES_ADDR
#define SPIKES_ADDR 0x08000000u /* = run_board.tcl */
#endif
#ifndef LABELS_ADDR
#define LABELS_ADDR 0x0F000000u /* = run_board.tcl */
#endif
#ifndef N_IMG_RUN
#define N_IMG_RUN 0 /* images to run; 0 = all images in spikes.bin */
#endif
#ifndef T_STEPS
#define T_STEPS 0 /* time steps per image; 0 = rows per image in spikes.bin (100) */
#endif
#ifndef PRINT_SPK
#define PRINT_SPK 1 /* print SPK lines in the latency phase */
#endif
#ifndef IDLE_MS
#define IDLE_MS 120000u /* duration of one IDLE power phase */
#endif
#ifndef CONT_MS
#define CONT_MS 120000u /* duration of one CONTINUOUS power phase (>= 60 s) */
#endif
#ifndef PROGRESS_MS
#define PROGRESS_MS 10000u /* progress line interval in the power phases */
#endif
#ifndef POWER_ROUNDS
#define POWER_ROUNDS 0 /* number of IDLE+CONT rounds; 0 = forever */
#endif
#ifndef IDLE_PS_ACTIVITY
#define IDLE_PS_ACTIVITY 1 /* 1: IDLE phase repeats the PS/AXI traffic of CONT (core in reset); 0: PS just spins */
#endif
#ifndef FCLK_MEAS_MS
#define FCLK_MEAS_MS 1000u /* window for measuring the PL clock against XTime */
#endif
#ifndef DDR_PTR /* the host co-simulation redirects DDR accesses */
#define DDR_PTR(a) ((const volatile u32 *)(UINTPTR)(a))
#endif
#define MAX_IMG 1000
#define MAX_OUT 16

/* ------------------------------------------------------------ register map */
#define R_ID 0x0000u
#define R_CTRL 0x0004u /* bit0 START (write 1), bit1 CORE_RST (1 = hold core in reset) */
#define R_STAT 0x0008u /* bit0 BUSY, bit1 DONE, bit2 OVF, bit3 CORE_READY, bit4 ERR, bit5 LOG_OVF */
#define R_T 0x000Cu
#define R_CYC 0x0010u
#define R_HID 0x0014u
#define R_NSPK 0x0018u
#define R_INFO 0x001Cu /* {N_OUT[31:24], N_IN[23:16], T_MAX[15:0]} */
#define R_WLO 0x0020u  /* read LO first: latches HI */
#define R_WHI 0x0024u
#define R_RUNS 0x0028u
#define R_COUNT 0x0040u /* + 4*c */
#define R_LOG 0x1000u   /* + 4*e : {t[15:8], class[7:0]} */
#define R_SBUF 0x4000u  /* + 4*w : spike-row buffer (write only) */
#define ID_VALUE 0x534E4E01u
#define MAGIC_S 0x534E4E53u
#define MAGIC_L 0x4C4E4E53u
#define ST_BUSY 0x1u
#define ST_DONE 0x2u
#define ST_OVF 0x4u
#define ST_ERR 0x10u
#define ST_LOGOVF 0x20u

static inline void wr(u32 off, u32 v) { Xil_Out32(SNN_BASE + off, v); }
static inline u32 rd(u32 off) { return Xil_In32(SNN_BASE + off); }
static u64 now(void) {
  XTime t;
  XTime_GetTime(&t);
  return (u64)t;
}
static u64 ticks_ms(u32 ms) { return (u64)COUNTS_PER_SECOND * ms / 1000u; }
static u32 ticks_to_ns(u64 t) { return (u32)(t * 1000000000ull / COUNTS_PER_SECOND); }
static u64 pl_wall(void) {
  u32 lo = rd(R_WLO);
  u32 hi = rd(R_WHI);
  return ((u64)hi << 32) | lo;
}

static u32 n_img, rows, n_in, n_out, T;
static const volatile u32 *spk_words; /* first word of image 0 */
static u32 lab_base;
static u32 cyc_ref[MAX_IMG];
static u32 fclk_hz;

typedef struct {
  u32 cyc, hid, ovf, nspk, stat, counts[MAX_OUT];
  u64 xt; /* XTime ticks from START write to DONE seen */
} result_t;

static u32 label_of(u32 k) {
  u32 w = DDR_PTR(lab_base + 8u + (k & ~3u))[0];
  return (w >> (8u * (k & 3u))) & 0xFFu;
}

/* copy image k (T rows) into the PL spike buffer; per row only up to the word
   holding the 0xFF terminator (the sequencer never reads further) */
static void load_image(u32 k) {
  const u32 wpr = n_in / 4u;
  for (u32 t = 0; t < T; t++) {
    const volatile u32 *row = spk_words + (k * rows + t) * wpr;
    for (u32 w = 0; w < wpr; w++) {
      u32 v = row[w];
      wr(R_SBUF + 4u * (t * wpr + w), v);
      if ((v & 0xFFu) == 0xFFu || (v & 0xFF00u) == 0xFF00u || (v & 0xFF0000u) == 0xFF0000u ||
          (v & 0xFF000000u) == 0xFF000000u)
        break;
    }
  }
}

/* START, wait for DONE, read the result registers */
static void run_image(result_t *r, int read_all) {
  u64 t0, t1;
  while (rd(R_STAT) & ST_BUSY) {
  }
  t0 = now();
  wr(R_CTRL, 1u); /* START */
  while (!((r->stat = rd(R_STAT)) & ST_DONE)) {
  }
  t1 = now();
  r->xt = t1 - t0;
  r->cyc = rd(R_CYC);
  r->ovf = (r->stat & ST_OVF) ? 1u : 0u;
  if (!read_all) return;
  r->hid = rd(R_HID);
  r->nspk = rd(R_NSPK);
  for (u32 c = 0; c < n_out; c++) r->counts[c] = rd(R_COUNT + 4u * c);
}

static void halt(const char *msg) {
  printf("FATAL: %s\r\n", msg);
  for (;;) {
  }
}

static u32 measure_fclk(void) {
  u64 w0 = pl_wall(), x0 = now(), x1, w1;
  while (now() - x0 < ticks_ms(FCLK_MEAS_MS)) {
  }
  w1 = pl_wall();
  x1 = now();
  return (u32)((w1 - w0) * (u64)COUNTS_PER_SECOND / (x1 - x0));
}

static void print_us(const char *tag, u64 ns) {
  printf("%s%lu.%03lu", tag, (unsigned long)(ns / 1000u), (unsigned long)(ns % 1000u));
}

/* ------------------------------------------------------------ phases */
static void phase_latency(void) {
  result_t r;
  u32 correct = 0, nospike = 0;
  u64 sum_cyc = 0, sum_ns = 0;
  u32 min_ns = 0xFFFFFFFFu, max_ns = 0;
  printf(">>> PHASE LATENCY START n_img=%lu T=%lu\r\n", (unsigned long)n_img, (unsigned long)T);
  for (u32 k = 0; k < n_img; k++) {
    u32 best = 0, lab = label_of(k), ns, hw_ns;
    load_image(k);
    run_image(&r, 1);
    if (r.stat & ST_ERR) halt("sequencer ERR (prefetch underrun) -- should never happen");
#if PRINT_SPK
    for (u32 e = 0; e < r.nspk && e < 1024u; e++) {
      u32 v = rd(R_LOG + 4u * e);
      printf("SPK %lu %lu %lu\r\n", (unsigned long)k, (unsigned long)((v >> 8) & 0xFFu), (unsigned long)(v & 0xFFu));
    }
    if (r.stat & ST_LOGOVF) printf("WARN image %lu: more than 1024 output spikes, SPK list truncated\r\n", (unsigned long)k);
#endif
    printf("IMG %lu LABEL %lu HID %lu OVF %lu CYCLES %lu COUNTS", (unsigned long)k, (unsigned long)lab,
           (unsigned long)r.hid, (unsigned long)r.ovf, (unsigned long)r.cyc);
    for (u32 c = 0; c < n_out; c++) {
      printf(" %lu", (unsigned long)r.counts[c]);
      if (r.counts[c] > r.counts[best]) best = c;
    }
    printf("\r\n");
    ns = ticks_to_ns(r.xt);
    hw_ns = (u32)((u64)r.cyc * 1000000000ull / fclk_hz);
    printf("TIME %lu XTIME_NS %lu HW_NS %lu\r\n", (unsigned long)k, (unsigned long)ns, (unsigned long)hw_ns);
    cyc_ref[k] = r.cyc;
    if (r.counts[best] == 0) nospike++;
    else if (best == lab) correct++;
    sum_cyc += r.cyc;
    sum_ns += ns;
    if (ns < min_ns) min_ns = ns;
    if (ns > max_ns) max_ns = ns;
  }
  printf("SUMMARY n=%lu correct=%lu (acc %lu.%02lu %%) nospike=%lu mean_cycles=%lu", (unsigned long)n_img,
         (unsigned long)correct, (unsigned long)(correct * 100u / n_img),
         (unsigned long)((correct * 10000u / n_img) % 100u), (unsigned long)nospike, (unsigned long)(sum_cyc / n_img));
  print_us(" mean_xtime_us=", sum_ns / n_img);
  print_us(" min_xtime_us=", min_ns);
  print_us(" max_xtime_us=", max_ns);
  print_us(" mean_hw_us=", sum_cyc * 1000000000ull / fclk_hz / n_img);
  printf(" fclk_hz=%lu\r\n", (unsigned long)fclk_hz);
  printf(">>> PHASE LATENCY END\r\n");
}

/* IDLE: core + sequencer held in reset (clock running).  With
   IDLE_PS_ACTIVITY=1 the PS repeats exactly the bus traffic of the CONT
   phase (copy image k into the spike buffer, then poll STATUS for as long as
   image k takes in hardware), so that (c)-(b) isolates the core's own power. */
static void phase_idle(u32 round) {
  u64 t0, next;
  u32 k = 0;
  wr(R_CTRL, 2u);
  printf(">>> PHASE IDLE round %lu START (core held in reset, PS traffic %s, %lu s; read the meter at 30/60/90 s)\r\n",
         (unsigned long)round, IDLE_PS_ACTIVITY ? "as in CONT" : "off", (unsigned long)(IDLE_MS / 1000u));
  t0 = now();
  next = ticks_ms(PROGRESS_MS);
  while (now() - t0 < ticks_ms(IDLE_MS)) {
    if (IDLE_PS_ACTIVITY) {
      u64 t1, dt = (u64)cyc_ref[k] * COUNTS_PER_SECOND / fclk_hz;
      load_image(k);
      t1 = now();
      while (now() - t1 < dt) (void)rd(R_STAT);
      if (++k == n_img) k = 0;
    }
    if (now() - t0 >= next) {
      printf("IDLE round %lu t=%lus\r\n", (unsigned long)round, (unsigned long)((now() - t0) / COUNTS_PER_SECOND));
      next += ticks_ms(PROGRESS_MS);
    }
  }
  printf(">>> PHASE IDLE round %lu END\r\n", (unsigned long)round);
}

static void phase_cont(u32 round) {
  result_t r;
  u64 t0, next, w0, busy = 0;
  u32 n = 0, mism = 0, k = 0;
  wr(R_CTRL, 0u); /* release the core */
  printf(">>> PHASE CONT round %lu START (continuous inference, %lu s; read the meter at 30/60/90 s)\r\n",
         (unsigned long)round, (unsigned long)(CONT_MS / 1000u));
  t0 = now();
  w0 = pl_wall();
  next = ticks_ms(PROGRESS_MS);
  while (now() - t0 < ticks_ms(CONT_MS)) {
    load_image(k);
    run_image(&r, 0);
    busy += r.cyc;
    if (r.cyc != cyc_ref[k]) mism++;
    n++;
    if (++k == n_img) k = 0;
    if (now() - t0 >= next) {
      u64 wall = pl_wall() - w0;
      printf("CONT round %lu t=%lus images=%lu duty=%lu.%01lu%% mismatches=%lu\r\n", (unsigned long)round,
             (unsigned long)((now() - t0) / COUNTS_PER_SECOND), (unsigned long)n,
             (unsigned long)(busy * 100u / wall), (unsigned long)((busy * 1000u / wall) % 10u), (unsigned long)mism);
      next += ticks_ms(PROGRESS_MS);
    }
  }
  {
    u64 wall = pl_wall() - w0;
    printf(">>> PHASE CONT round %lu END images=%lu busy_kcycles=%lu wall_kcycles=%lu duty=%lu.%01lu%% "
           "cycle_mismatches=%lu\r\n",
           (unsigned long)round, (unsigned long)n, (unsigned long)(busy / 1000u), (unsigned long)(wall / 1000u),
           (unsigned long)(busy * 100u / wall), (unsigned long)((busy * 1000u / wall) % 10u), (unsigned long)mism);
  }
  wr(R_CTRL, 2u); /* back to idle */
}

#ifndef APP_MAIN /* the host co-simulation renames it */
#define APP_MAIN main
#endif
int APP_MAIN(void) {
  u32 id, info, t_max;
  const volatile u32 *hdr = DDR_PTR(SPIKES_ADDR);
  const volatile u32 *lhdr = DDR_PTR(LABELS_ADDR);

  printf("\r\n=== HASTE V4 on-board measurement (snn_board) ===\r\n");
  Xil_DCacheInvalidateRange((UINTPTR)SPIKES_ADDR, 16u);
  if (hdr[0] != MAGIC_S) halt("spikes.bin not found at SPIKES_ADDR (dow -data spikes.bin 0x08000000)");
  if (lhdr[0] != MAGIC_L) halt("labels.bin not found at LABELS_ADDR (dow -data labels.bin 0x0F000000)");
  n_img = hdr[1];
  rows = hdr[2];
  n_in = hdr[3];
  Xil_DCacheInvalidateRange((UINTPTR)SPIKES_ADDR, 16u + n_img * rows * n_in);
  Xil_DCacheInvalidateRange((UINTPTR)LABELS_ADDR, 8u + n_img);
  if (lhdr[1] != n_img) halt("labels.bin and spikes.bin have different image counts");
  spk_words = DDR_PTR(SPIKES_ADDR + 16u);
  lab_base = LABELS_ADDR;
  if (N_IMG_RUN > 0 && N_IMG_RUN < n_img) n_img = N_IMG_RUN;
  if (n_img > MAX_IMG) n_img = MAX_IMG;

  id = rd(R_ID);
  info = rd(R_INFO);
  if (id != ID_VALUE) halt("wrapper ID mismatch: wrong bitstream or SNN_BASE");
  n_out = info >> 24;
  t_max = info & 0xFFFFu;
  T = T_STEPS ? T_STEPS : rows;
  printf("ID %08lx  N_OUT %lu  N_IN %lu  T_MAX %lu | data: n_img %lu rows %lu n_in %lu | T %lu\r\n",
         (unsigned long)id, (unsigned long)n_out, (unsigned long)((info >> 16) & 0xFFu), (unsigned long)t_max,
         (unsigned long)n_img, (unsigned long)rows, (unsigned long)n_in, (unsigned long)T);
  if (((info >> 16) & 0xFFu) != n_in) halt("N_IN of the bitstream differs from spikes.bin");
  if (T > rows || T > t_max || n_out > MAX_OUT) halt("bad T / N_OUT");

  /* clean start: pulse the core reset once (as at the start of tb_snn), then configure */
  wr(R_CTRL, 2u);
  wr(R_CTRL, 0u);
  wr(R_T, T);
  fclk_hz = measure_fclk();
  printf("FCLK measured %lu Hz (PL wall counter vs XTime, %lu ms window); XTime %lu Hz\r\n", (unsigned long)fclk_hz,
         (unsigned long)FCLK_MEAS_MS, (unsigned long)COUNTS_PER_SECOND);

  phase_latency();
  for (u32 round = 1; POWER_ROUNDS == 0 || round <= POWER_ROUNDS; round++) {
    phase_idle(round);
    phase_cont(round);
  }
  wr(R_CTRL, 2u);
  printf(">>> DONE (core idle in reset)\r\n");
  return 0;
}
