import numpy as np
from keras import backend as K
from keras.layers import InputSpec, Layer, Dense, Conv2D, SeparableConv2D
from keras import constraints
from keras import initializers
from keras import regularizers
from keras.utils import conv_utils
from binary_ops import binarize


class Clip(constraints.Constraint):
    def __init__(self, min_value, max_value=None):
        self.min_value = min_value
        self.max_value = max_value
        if not self.max_value:
            self.max_value = -self.min_value
        if self.min_value > self.max_value:
            self.min_value, self.max_value = self.max_value, self.min_value

    def __call__(self, p):
        return K.clip(p, self.min_value, self.max_value)

    def get_config(self):
        return {"min_value": self.min_value,
                "max_value": self.max_value}


class BinaryDense(Dense):
    def __init__(self, units, H=1., kernel_lr_multiplier='Glorot', bias_lr_multiplier=None, **kwargs):
        super(BinaryDense, self).__init__(units, **kwargs)
        self.H = H
        self.kernel_lr_multiplier = kernel_lr_multiplier
        self.bias_lr_multiplier = bias_lr_multiplier
        
        super(BinaryDense, self).__init__(units, **kwargs)
    
    def build(self, input_shape):
        assert len(input_shape) >= 2
        input_dim = input_shape[1]

        if self.H == 'Glorot':
            self.H = np.float32(np.sqrt(1.5 / (input_dim + self.units)))
        if self.kernel_lr_multiplier == 'Glorot':
            self.kernel_lr_multiplier = np.float32(1. / np.sqrt(1.5 / (input_dim + self.units)))
            
        self.kernel_constraint = Clip(-self.H, self.H)
        self.kernel_initializer = initializers.RandomUniform(-self.H, self.H)
        self.kernel = self.add_weight(shape=(input_dim, self.units),
                                     initializer=self.kernel_initializer,
                                     name='kernel',
                                     regularizer=self.kernel_regularizer,
                                     constraint=self.kernel_constraint)
        if self.use_bias:
            self.lr_multipliers = [self.kernel_lr_multiplier, self.bias_lr_multiplier]
            self.bias = self.add_weight(shape=(self.output_dim,),
                                     initializer=self.bias_initializer,
                                     name='bias',
                                     regularizer=self.bias_regularizer,
                                     constraint=self.bias_constraint)
        else:
            self.lr_multipliers = [self.kernel_lr_multiplier]
            self.bias = None

        self.input_spec = InputSpec(min_ndim=2, axes={-1: input_dim})
        self.built = True


    def call(self, inputs):
        binary_kernel = binarize(self.kernel, H=self.H)
        output = K.dot(inputs, binary_kernel)
        if self.use_bias:
            output = K.bias_add(output, self.bias)
        if self.activation is not None:
            output = self.activation(output)
        return output
        
    def get_config(self):
        config = {'H': self.H,
                  'kernel_lr_multiplier': self.kernel_lr_multiplier,
                  'bias_lr_multiplier': self.bias_lr_multiplier}
        base_config = super(BinaryDense, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class BinaryConv2D(Conv2D):
    def __init__(self, filters, kernel_lr_multiplier='Glorot', 
                 bias_lr_multiplier=None, H=1., **kwargs):
        super(BinaryConv2D, self).__init__(filters, **kwargs)
        self.H = H
        self.kernel_lr_multiplier = kernel_lr_multiplier
        self.bias_lr_multiplier = bias_lr_multiplier
        
        
    def build(self, input_shape):
        if self.data_format == 'channels_first':
            channel_axis = 1
        else:
            channel_axis = -1 
        if input_shape[channel_axis] is None:
                raise ValueError('The channel dimension of the inputs '
                                 'should be defined. Found `None`.')

        input_dim = input_shape[channel_axis]
        kernel_shape = self.kernel_size + (input_dim, self.filters)
            
        base = self.kernel_size[0] * self.kernel_size[1]
        if self.H == 'Glorot':
            nb_input = int(input_dim * base)
            nb_output = int(self.filters * base)
            self.H = np.float32(np.sqrt(1.5 / (nb_input + nb_output)))
            
        if self.kernel_lr_multiplier == 'Glorot':
            nb_input = int(input_dim * base)
            nb_output = int(self.filters * base)
            self.kernel_lr_multiplier = np.float32(1. / np.sqrt(1.5/ (nb_input + nb_output)))

        self.kernel_constraint = Clip(-self.H, self.H)
        self.kernel_initializer = initializers.RandomUniform(-self.H, self.H)
        self.kernel = self.add_weight(shape=kernel_shape,
                                 initializer=self.kernel_initializer,
                                 name='kernel',
                                 regularizer=self.kernel_regularizer,
                                 constraint=self.kernel_constraint)

        if self.use_bias:
            self.lr_multipliers = [self.kernel_lr_multiplier, self.bias_lr_multiplier]
            self.bias = self.add_weight((self.output_dim,),
                                     initializer=self.bias_initializers,
                                     name='bias',
                                     regularizer=self.bias_regularizer,
                                     constraint=self.bias_constraint)

        else:
            self.lr_multipliers = [self.kernel_lr_multiplier]
            self.bias = None

        self.input_spec = InputSpec(ndim=4, axes={channel_axis: input_dim})
        self.built = True

    def call(self, inputs):
        binary_kernel = binarize(self.kernel, H=self.H) 
        outputs = K.conv2d(
            inputs,
            binary_kernel,
            strides=self.strides,
            padding=self.padding,
            data_format=self.data_format,
            dilation_rate=self.dilation_rate)

        if self.use_bias:
            outputs = K.bias_add(
                outputs,
                self.bias,
                data_format=self.data_format)

        if self.activation is not None:
            return self.activation(outputs)
        return outputs
        
    def get_config(self):
        config = {'H': self.H,
                  'kernel_lr_multiplier': self.kernel_lr_multiplier,
                  'bias_lr_multiplier': self.bias_lr_multiplier}
        base_config = super(BinaryConv2D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class SeparableBinaryConv2D(SeparableConv2D):
    def __init__(self, filters, kernel_lr_multiplier='Glorot', 
                 bias_lr_multiplier=None, H=1., **kwargs):
        super(SeparableBinaryConv2D, self).__init__(filters, **kwargs)
        self.H = H
        self.kernel_lr_multiplier = kernel_lr_multiplier
        self.bias_lr_multiplier = bias_lr_multiplier
        self.depth_multiplier = 1
        
        
    def build(self, input_shape):
        if self.data_format == 'channels_first':
            channel_axis = 1
        else:
            channel_axis = -1 
        if input_shape[channel_axis] is None:
                raise ValueError('The channel dimension of the inputs '
                                 'should be defined. Found `None`.')

        input_dim = input_shape[channel_axis]
        kernel_shape = self.kernel_size + (input_dim, self.filters)
            
        base = self.kernel_size[0] * self.kernel_size[1]
        if self.H == 'Glorot':
            nb_input = int(input_dim * base)
            nb_output = int(self.filters * base)
            self.H = np.float32(np.sqrt(1.5 / (nb_input + nb_output)))
            
        if self.kernel_lr_multiplier == 'Glorot':
            nb_input = int(input_dim * base)
            nb_output = int(self.filters * base)
            self.kernel_lr_multiplier = np.float32(1. / np.sqrt(1.5/ (nb_input + nb_output)))

        self.depthwise_constraint = Clip(-self.H, self.H)
        self.depthwise_initializer = initializers.RandomUniform(-self.H, self.H)
        
        depthwise_kernel_shape = (input_dim, self.depth_multiplier)
        depthwise_kernel_shape = self.kernel_size + depthwise_kernel_shape
        pointwise_kernel_shape = (self.depth_multiplier * input_dim, self.filters)
        pointwise_kernel_shape = (1,) * 2 + pointwise_kernel_shape

        self.depthwise_kernel = self.add_weight(
            shape=depthwise_kernel_shape,
            initializer=self.depthwise_initializer,
            name='depthwise_kernel',
            regularizer=self.depthwise_regularizer,
            constraint=self.depthwise_constraint)

        self.pointwise_kernel = self.add_weight(
            shape=pointwise_kernel_shape,
            initializer=self.pointwise_initializer,
            name='pointwise_kernel',
            regularizer=self.pointwise_regularizer,
            constraint=self.pointwise_constraint)

        if self.use_bias:
            self.lr_multipliers = [self.kernel_lr_multiplier, self.bias_lr_multiplier]
            self.bias = self.add_weight((self.output_dim,),
                                     initializer=self.bias_initializers,
                                     name='bias',
                                     regularizer=self.bias_regularizer,
                                     constraint=self.bias_constraint)

        else:
            self.lr_multipliers = [self.kernel_lr_multiplier]
            self.bias = None

        # Set input spec.
        self.input_spec = InputSpec(ndim=4, axes={channel_axis: input_dim})
        self.built = True

    def call(self, inputs):
        depthwise_kernel = binarize(self.depthwise_kernel, H=self.H) 
        pointwise_kernel = binarize(self.pointwise_kernel, H=self.H)
        outputs = K.separable_conv2d(
            inputs,
            depthwise_kernel,
            pointwise_kernel,
            strides=self.strides,
            padding=self.padding,
            data_format=self.data_format,
            dilation_rate=self.dilation_rate)

        if self.use_bias:
            outputs = K.bias_add(
                outputs,
                self.bias,
                data_format=self.data_format)

        if self.activation is not None:
            return self.activation(outputs)
        return outputs
        
    def get_config(self):
        config = {'H': self.H,
                  'kernel_lr_multiplier': self.kernel_lr_multiplier,
                  'bias_lr_multiplier': self.bias_lr_multiplier}
        base_config = super(SeparableBinaryConv2D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


# Aliases
BinaryConvolution2D = BinaryConv2D
SeparableBinaryConvolution2D = SeparableBinaryConv2D
