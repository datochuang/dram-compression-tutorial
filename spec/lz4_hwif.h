/* LZ4 accelerator HW/FW interface, version 0.1-draft.
 * Generated from sim/ifsim/interface.json by `python3 sim/run_if.py gen-spec`. Do not edit by hand.
 * All multi-byte fields are little-endian. */
#ifndef LZ4_HWIF_H
#define LZ4_HWIF_H

#include <stdint.h>

/* Constants */
#define LZ4_PAGE_SIZE              4096u
#define LZ4_CHUNK_SIZE             512u
#define LZ4_CHUNK_SLOTS            8u
#define LZ4_JOB_SLOT_SIZE          64u
#define LZ4_CPL_SLOT_SIZE          16u
#define LZ4_COT_ENTRY_SIZE         32u
#define LZ4_RING_ALIGN             64u
#define LZ4_ID_VALUE               0x4C5A0001u

/* Register offsets */
#define LZ4_REG_ID                 0x00u   /* RO */
#define LZ4_REG_CAP                0x04u   /* RO */
#define LZ4_REG_CTRL               0x08u   /* RW */
#define LZ4_REG_STATUS             0x0Cu   /* RO */
#define LZ4_REG_IRQ_STATUS         0x10u   /* RO/W1C */
#define LZ4_REG_IRQ_ENABLE         0x14u   /* RW */
#define LZ4_REG_ERR_CODE           0x18u   /* RO */
#define LZ4_REG_JOB_BASE           0x20u   /* RW */
#define LZ4_REG_JOB_SIZE           0x24u   /* RW */
#define LZ4_REG_JOB_TAIL           0x28u   /* RW */
#define LZ4_REG_JOB_HEAD           0x2Cu   /* RO */
#define LZ4_REG_CPL_BASE           0x30u   /* RW */
#define LZ4_REG_CPL_SIZE           0x34u   /* RW */
#define LZ4_REG_CPL_TAIL           0x38u   /* RO */
#define LZ4_REG_CPL_HEAD           0x3Cu   /* RW */
#define LZ4_REG_POOL_BASE          0x40u   /* RW */
#define LZ4_REG_POOL_CHUNKS        0x44u   /* RW */
#define LZ4_REG_FRAME_BASE         0x48u   /* RW */
#define LZ4_REG_FRAME_COUNT        0x4Cu   /* RW */

/* Register fields */
#define LZ4_CAP_CHUNK_SLOTS_SHIFT          0u
#define LZ4_CAP_CHUNK_SLOTS_MASK           0x0000000Fu
#define LZ4_CAP_CHUNK_SHIFT_SHIFT          4u
#define LZ4_CAP_CHUNK_SHIFT_MASK           0x000000F0u
#define LZ4_CAP_PAGE_SHIFT_SHIFT           8u
#define LZ4_CAP_PAGE_SHIFT_MASK            0x00000F00u
#define LZ4_CAP_RING_SHIFT_MAX_SHIFT       12u
#define LZ4_CAP_RING_SHIFT_MAX_MASK        0x0000F000u
#define LZ4_CAP_ENGINES_SHIFT              16u
#define LZ4_CAP_ENGINES_MASK               0x000F0000u
#define LZ4_CTRL_ENABLE_SHIFT              0u
#define LZ4_CTRL_ENABLE_MASK               0x00000001u
#define LZ4_CTRL_SOFT_RESET_SHIFT          1u
#define LZ4_CTRL_SOFT_RESET_MASK           0x00000002u
#define LZ4_STATUS_BUSY_SHIFT              0u
#define LZ4_STATUS_BUSY_MASK               0x00000001u
#define LZ4_STATUS_HALTED_SHIFT            1u
#define LZ4_STATUS_HALTED_MASK             0x00000002u
#define LZ4_IRQ_STATUS_DONE_SHIFT          0u
#define LZ4_IRQ_STATUS_DONE_MASK           0x00000001u
#define LZ4_IRQ_STATUS_ERROR_SHIFT         1u
#define LZ4_IRQ_STATUS_ERROR_MASK          0x00000002u
#define LZ4_IRQ_ENABLE_DONE_SHIFT          0u
#define LZ4_IRQ_ENABLE_DONE_MASK           0x00000001u
#define LZ4_IRQ_ENABLE_ERROR_SHIFT         1u
#define LZ4_IRQ_ENABLE_ERROR_MASK          0x00000002u

/* opcode */
enum lz4_opcode {
    LZ4_OPCODE_COMPRESS = 1,
    LZ4_OPCODE_DECOMPRESS = 2,
};

/* status */
enum lz4_status {
    LZ4_STATUS_OK = 0,
    LZ4_STATUS_INCOMPRESSIBLE = 1,
    LZ4_STATUS_BAD_STREAM = 3,
    LZ4_STATUS_BUS_ERROR = 5,
    LZ4_STATUS_BAD_DESC = 6,
};

/* bad_desc */
enum lz4_bad_desc {
    LZ4_BAD_DESC_OPCODE = 1,
    LZ4_BAD_DESC_COUNT = 2,
    LZ4_BAD_DESC_CHUNK_RANGE = 3,
    LZ4_BAD_DESC_FRAME_RANGE = 4,
    LZ4_BAD_DESC_LENGTH = 5,
};

/* halt_code */
enum lz4_halt_code {
    LZ4_HALT_CODE_NONE = 0,
    LZ4_HALT_CODE_BAD_RING_CFG = 1,
    LZ4_HALT_CODE_RING_BUS_ERROR = 2,
    LZ4_HALT_CODE_BAD_INDEX = 3,
};

/* flag */
#define LZ4_FLAG_VALID             0x01u
#define LZ4_FLAG_RO                0x02u
#define LZ4_FLAG_RAW               0x04u

struct lz4_job_desc {
    uint8_t  opcode;   /* 0x00 */
    uint8_t  count;   /* 0x01 */
    uint16_t limit;   /* 0x02 */
    uint32_t frame_pa;   /* 0x04 */
    uint16_t comp_len;   /* 0x08 */
    uint16_t flags;   /* 0x0A */
    uint32_t checksum;   /* 0x0C */
    uint32_t tag;   /* 0x10 */
    uint8_t  chunk[8][3];   /* 0x14: 8 numbers of 24 bits */
    uint32_t rsvd;   /* 0x2C */
};
_Static_assert(sizeof(struct lz4_job_desc) == 48, "lz4_job_desc size");

struct lz4_completion {
    uint8_t  status;   /* 0x00 */
    uint8_t  flags;   /* 0x01 */
    uint16_t length;   /* 0x02 */
    uint32_t checksum;   /* 0x04 */
    uint32_t tag;   /* 0x08 */
    uint32_t aux;   /* 0x0C */
};
_Static_assert(sizeof(struct lz4_completion) == 16, "lz4_completion size");

struct lz4_cot_entry {
    uint8_t  flags;   /* 0x00 */
    uint8_t  count;   /* 0x01 */
    uint16_t comp_len;   /* 0x02 */
    uint32_t checksum;   /* 0x04 */
    uint8_t  chunk[8][3];   /* 0x08: 8 numbers of 24 bits */
};
_Static_assert(sizeof(struct lz4_cot_entry) == 32, "lz4_cot_entry size");

/* A chunk number is 24 bits, stored low byte first. */
static inline uint32_t lz4_chunk_get(const uint8_t c[3])
{
    return (uint32_t)c[0] | ((uint32_t)c[1] << 8) | ((uint32_t)c[2] << 16);
}
static inline void lz4_chunk_set(uint8_t c[3], uint32_t n)
{
    c[0] = (uint8_t)n; c[1] = (uint8_t)(n >> 8); c[2] = (uint8_t)(n >> 16);
}

/* Rule ids of the interface spec, for assertions and log messages. */
#define LZ4_RULE_FW_CFG_1       "FW-CFG-1"
#define LZ4_RULE_FW_CFG_2       "FW-CFG-2"
#define LZ4_RULE_FW_JOB_1       "FW-JOB-1"
#define LZ4_RULE_FW_JOB_2       "FW-JOB-2"
#define LZ4_RULE_FW_JOB_3       "FW-JOB-3"
#define LZ4_RULE_FW_JOB_4       "FW-JOB-4"
#define LZ4_RULE_FW_JOB_5       "FW-JOB-5"
#define LZ4_RULE_FW_JOB_6       "FW-JOB-6"
#define LZ4_RULE_FW_CPL_1       "FW-CPL-1"
#define LZ4_RULE_FW_CPL_2       "FW-CPL-2"
#define LZ4_RULE_FW_MM_1        "FW-MM-1"
#define LZ4_RULE_FW_MM_2        "FW-MM-2"
#define LZ4_RULE_FW_MM_3        "FW-MM-3"
#define LZ4_RULE_FW_MM_4        "FW-MM-4"
#define LZ4_RULE_FW_MM_5        "FW-MM-5"
#define LZ4_RULE_FW_MM_6        "FW-MM-6"
#define LZ4_RULE_FW_MM_7        "FW-MM-7"
#define LZ4_RULE_FW_CACHE_1     "FW-CACHE-1"
#define LZ4_RULE_FW_CACHE_2     "FW-CACHE-2"
#define LZ4_RULE_FW_CACHE_3     "FW-CACHE-3"
#define LZ4_RULE_FW_CACHE_4     "FW-CACHE-4"
#define LZ4_RULE_FW_CACHE_5     "FW-CACHE-5"
#define LZ4_RULE_FW_RST_1       "FW-RST-1"
#define LZ4_RULE_HW_MEM_1       "HW-MEM-1"
#define LZ4_RULE_HW_MEM_2       "HW-MEM-2"
#define LZ4_RULE_HW_CPL_1       "HW-CPL-1"
#define LZ4_RULE_HW_CPL_2       "HW-CPL-2"
#define LZ4_RULE_HW_CPL_3       "HW-CPL-3"
#define LZ4_RULE_HW_IRQ_1       "HW-IRQ-1"
#define LZ4_RULE_HW_DATA_1      "HW-DATA-1"
#define LZ4_RULE_HW_DATA_2      "HW-DATA-2"
#define LZ4_RULE_HW_STATE_1     "HW-STATE-1"
#define LZ4_RULE_HW_RST_1       "HW-RST-1"
#define LZ4_RULE_AUDIT_1        "AUDIT-1"
#define LZ4_RULE_AUDIT_2        "AUDIT-2"
#define LZ4_RULE_AUDIT_3        "AUDIT-3"
#define LZ4_RULE_AUDIT_4        "AUDIT-4"

#endif /* LZ4_HWIF_H */
