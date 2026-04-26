#ifdef __SDCC_mcs51
unsigned long
callee_u32(void) __iar
{
  return 0x12345678ul;
}

unsigned long
caller_u32(void)
{
  return callee_u32();
}
#endif
