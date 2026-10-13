// avtbridge - tiny command-line bridge to macOS's private AvatarKit framework.
//
// UNSUPPORTED: AvatarKit is a private Apple framework. Nothing here ships Apple
// content; it loads the framework already installed on the user's Mac. Selectors
// were discovered via the Objective-C runtime and may change in any macOS update.
//
// Usage:
//   avtbridge catalog                       all categories, preset ids and color names (JSON)
//   avtbridge poses                         all sticker poses with labels (JSON)
//   avtbridge neutral                       the neutral descriptor (JSON)
//   avtbridge normalize <in.json>           descriptor after AvatarKit has loaded it (JSON);
//                                           invalid ids are silently replaced, so diff against input
//   avtbridge render <in.json> <size> <margin> <pose>=<out.png> [<pose>=<out.png> ...]
//                                           square PNGs, trimmed to the avatar and centered

#import <AppKit/AppKit.h>
#import <Foundation/Foundation.h>
#import <dlfcn.h>
#import <objc/message.h>

static NSString *const kAvatarKitPath = @"/System/Library/PrivateFrameworks/AvatarKit.framework/AvatarKit";
// Packs searched for poses, in order. "stickers" is what Messages shows; "posesPack" adds portrait poses.
static NSArray<NSString *> *PosePacks(void) { return @[ @"stickers", @"posesPack" ]; }
static void *gAvatarKit;

static int fail(NSString *what, NSError *err) {
  fprintf(stderr, "avtbridge: %s%s%s\n", what.UTF8String, err ? ": " : "", err ? err.localizedDescription.UTF8String : "");
  return 1;
}

static void printJSON(id obj) {
  NSData *data = [NSJSONSerialization dataWithJSONObject:obj options:NSJSONWritingSortedKeys | NSJSONWritingPrettyPrinted error:nil];
  fwrite(data.bytes, 1, data.length, stdout);
  fputc('\n', stdout);
}

static NSDictionary *encodeDescriptor(id descriptor) {
  NSMutableDictionary *out = [NSMutableDictionary dictionary];
  ((void (*)(id, SEL, id))objc_msgSend)(descriptor, sel_registerName("encodeInDictionaryRepresentation:"), out);
  return out;
}

static id loadDescriptor(NSString *path, NSError **err) {
  NSData *data = [NSData dataWithContentsOfFile:path options:0 error:err];
  if (!data) return nil;
  NSDictionary *dict = [NSJSONSerialization JSONObjectWithData:data options:0 error:err];
  if (![dict isKindOfClass:[NSDictionary class]]) return nil;
  return ((id (*)(id, SEL, id, NSError **))objc_msgSend)(
      [NSClassFromString(@"AVTMemojiDescriptor") alloc], sel_registerName("initWithDictionaryRepresentation:error:"), dict, err);
}

static id makeAvatar(id descriptor, NSError **err) {
  return ((id (*)(id, SEL, id, NSInteger, NSError **))objc_msgSend)(
      [NSClassFromString(@"AVTMemoji") alloc], sel_registerName("initWithDescriptor:usageIntent:error:"), descriptor, (NSInteger)0, err);
}

static NSArray<NSString *> *poseNamesInPack(NSString *pack) {
  return ((id (*)(id, SEL, id))objc_msgSend)(
             NSClassFromString(@"AVTStickerConfiguration"), sel_registerName("availableStickerNamesForMemojiInStickerPack:"), pack)
      ?: @[];
}

static id poseConfiguration(NSString *pose) {
  for (NSString *pack in PosePacks())
    if ([poseNamesInPack(pack) containsObject:pose])
      return ((id (*)(id, SEL, id, id))objc_msgSend)(NSClassFromString(@"AVTStickerConfiguration"),
                                                     sel_registerName("stickerConfigurationForMemojiInStickerPack:stickerName:"), pack, pose);
  return nil;
}

static int cmdCatalog(void) {
  NSString *(*categoryName)(NSInteger) = dlsym(gAvatarKit, "AVTPresetCategoryToString");
  if (!categoryName) return fail(@"AVTPresetCategoryToString not found", nil);
  Class preset = NSClassFromString(@"AVTPreset");
  NSMutableDictionary *out = [NSMutableDictionary dictionary];
  for (NSInteger i = 0; i < 64; i++) {
    NSString *name = categoryName(i);
    if (!name.length) continue;
    NSMutableArray *presets = [NSMutableArray array];
    for (id p in ((NSArray * (*)(id, SEL, NSInteger)) objc_msgSend)(preset, sel_registerName("availablePresetsForCategory:"), i))
      [presets addObject:@{@"id" : [p valueForKey:@"identifier"] ?: @"", @"label" : [p valueForKey:@"localizedName"] ?: @""}];
    NSMutableArray *colors = [NSMutableArray array];  // index 0 = colors, 1 = secondaryColors, 2 = tertiaryColors
    for (NSInteger ci = 0; ci < 3; ci++) {
      NSMutableArray *names = [NSMutableArray array];
      for (id c in ((NSArray * (*)(id, SEL, NSInteger, NSInteger)) objc_msgSend)(preset, sel_registerName("colorPresetsForCategory:colorIndex:"), i, ci))
        [names addObject:@{@"name" : [c valueForKey:@"name"] ?: @"", @"label" : [c valueForKey:@"localizedName"] ?: @""}];
      [colors addObject:names];
    }
    out[name] = @{@"presets" : presets, @"colors" : colors};
  }
  printJSON(out);
  return 0;
}

static int cmdPoses(void) {
  NSMutableArray *out = [NSMutableArray array];
  NSMutableSet *seen = [NSMutableSet set];
  for (NSString *pack in PosePacks()) {
    for (NSString *name in poseNamesInPack(pack)) {
      if ([seen containsObject:name]) continue;
      [seen addObject:name];
      id config = poseConfiguration(name);
      [out addObject:@{
        @"name" : name,
        @"pack" : pack,
        @"label" : [config valueForKey:@"localizedName"] ?: @"",
        @"emoji" : [config valueForKey:@"emojiRepresentation"] ?: @"",
      }];
    }
  }
  printJSON(out);
  return 0;
}

static int cmdNeutral(void) {
  id descriptor = ((id (*)(id, SEL))objc_msgSend)(NSClassFromString(@"AVTMemoji"), sel_registerName("neutralMemojiDescriptor"));
  if (!descriptor) return fail(@"neutralMemojiDescriptor returned nil", nil);
  printJSON(encodeDescriptor(descriptor));
  return 0;
}

static int cmdNormalize(NSString *in) {
  NSError *err = nil;
  id descriptor = loadDescriptor(in, &err);
  if (!descriptor) return fail(@"could not read descriptor", err);
  id avatar = makeAvatar(descriptor, &err);
  if (!avatar) return fail(@"could not build avatar", err);
  printJSON(encodeDescriptor(((id (*)(id, SEL))objc_msgSend)(avatar, sel_registerName("newDescriptor"))));
  return 0;
}

// Crops to the non-transparent pixels, then centers that on a transparent square canvas.
static CGImageRef squareFit(CGImageRef src, size_t size, CGFloat margin) {
  size_t w = CGImageGetWidth(src), h = CGImageGetHeight(src);
  CGColorSpaceRef space = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
  CGContextRef scan = CGBitmapContextCreate(NULL, w, h, 8, w * 4, space, kCGImageAlphaPremultipliedLast);
  CGContextDrawImage(scan, CGRectMake(0, 0, w, h), src);
  const uint8_t *px = CGBitmapContextGetData(scan);
  size_t minX = w, minY = h, maxX = 0, maxY = 0;  // rows are top-down in memory
  for (size_t y = 0; y < h; y++)
    for (size_t x = 0; x < w; x++)
      if (px[(y * w + x) * 4 + 3] > 8) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
  CGContextRelease(scan);
  CGImageRef cropped = maxX >= minX ? CGImageCreateWithImageInRect(src, CGRectMake(minX, minY, maxX - minX + 1, maxY - minY + 1))
                                    : CGImageRetain(src);

  CGFloat cw = CGImageGetWidth(cropped), ch = CGImageGetHeight(cropped);
  CGFloat box = size * (1 - 2 * margin), scale = MIN(box / cw, box / ch);
  CGRect dest = CGRectMake((size - cw * scale) / 2, (size - ch * scale) / 2, cw * scale, ch * scale);
  CGContextRef out = CGBitmapContextCreate(NULL, size, size, 8, size * 4, space, kCGImageAlphaPremultipliedLast);
  CGContextSetInterpolationQuality(out, kCGInterpolationHigh);
  CGContextDrawImage(out, dest, cropped);
  CGImageRef result = CGBitmapContextCreateImage(out);
  CGContextRelease(out);
  CGImageRelease(cropped);
  CGColorSpaceRelease(space);
  return result;
}

static int cmdRender(NSString *in, size_t size, CGFloat margin, NSArray<NSString *> *jobs) {
  NSError *err = nil;
  id descriptor = loadDescriptor(in, &err);
  if (!descriptor) return fail(@"could not read descriptor", err);
  id avatar = makeAvatar(descriptor, &err);
  if (!avatar) return fail(@"could not build avatar", err);
  id generator = ((id (*)(id, SEL, id))objc_msgSend)([NSClassFromString(@"AVTStickerGenerator") alloc], sel_registerName("initWithAvatar:"), avatar);
  // Render at 2x the requested size so the trimmed avatar still has enough pixels.
  id options = ((id (*)(id, SEL, BOOL))objc_msgSend)(NSClassFromString(@"AVTStickerGeneratorOptions"), sel_registerName("optionsWithCorrectClipping:"), YES);
  ((void (*)(id, SEL, double))objc_msgSend)(options, sel_registerName("setSizeMultiplier:"), MAX(1.0, size * 2.0 / 420.0));

  int failures = 0;
  for (NSString *job in jobs) {
    NSRange eq = [job rangeOfString:@"="];
    if (eq.location == NSNotFound) { failures += fail([NSString stringWithFormat:@"expected <pose>=<out.png>, got %@", job], nil); continue; }
    NSString *pose = [job substringToIndex:eq.location], *outPath = [job substringFromIndex:eq.location + 1];
    id config = poseConfiguration(pose);
    if (!config) { failures += fail([NSString stringWithFormat:@"unknown pose %@", pose], nil); continue; }

    __block NSImage *image = nil;
    __block BOOL done = NO;
    ((void (*)(id, SEL, id, id, id))objc_msgSend)(generator, sel_registerName("stickerImageWithConfiguration:options:completionHandler:"), config, options,
                                                  ^(id result) { image = result; done = YES; });
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:60];
    while (!done && deadline.timeIntervalSinceNow > 0)
      [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
    if (![image isKindOfClass:[NSImage class]]) { failures += fail([NSString stringWithFormat:@"pose %@ did not render", pose], nil); continue; }

    CGImageRef fitted = squareFit([image CGImageForProposedRect:NULL context:nil hints:nil], size, margin);
    NSData *png = [[[NSBitmapImageRep alloc] initWithCGImage:fitted] representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
    CGImageRelease(fitted);
    if (![png writeToFile:outPath options:NSDataWritingAtomic error:&err]) { failures += fail(@"could not write PNG", err); continue; }
    printf("%s\n", outPath.UTF8String);
  }
  return failures ? 1 : 0;
}

int main(int argc, const char **argv) {
  @autoreleasepool {
    if (argc < 2) {
      fprintf(stderr, "usage: avtbridge catalog | poses | neutral | normalize <in.json> | render <in.json> <size> <margin> <pose>=<out.png>...\n");
      return 2;
    }
    gAvatarKit = dlopen(kAvatarKitPath.fileSystemRepresentation, RTLD_NOW);
    if (!gAvatarKit) return fail([NSString stringWithFormat:@"dlopen failed: %s", dlerror()], nil);
    NSString *cmd = @(argv[1]);
    if ([cmd isEqualToString:@"catalog"]) return cmdCatalog();
    if ([cmd isEqualToString:@"poses"]) return cmdPoses();
    if ([cmd isEqualToString:@"neutral"]) return cmdNeutral();
    if ([cmd isEqualToString:@"normalize"] && argc >= 3) return cmdNormalize(@(argv[2]));
    if ([cmd isEqualToString:@"render"] && argc >= 6) {
      NSMutableArray *jobs = [NSMutableArray array];
      for (int i = 5; i < argc; i++) [jobs addObject:@(argv[i])];
      return cmdRender(@(argv[2]), (size_t)atol(argv[3]), atof(argv[4]), jobs);
    }
    return fail([NSString stringWithFormat:@"unknown or incomplete command: %@", cmd], nil);
  }
}
